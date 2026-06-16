const evidenceCache = new Map()

function buildBingSearchUrl(queryParts) {
	const query = queryParts.filter(Boolean).join(" ")
	const params = new URLSearchParams({
		q: query,
		setlang: "zh-Hans",
		cc: "cn",
		mkt: "zh-CN",
	})
	return `https://www.bing.com/search?${params.toString()}`
}

async function fetchText(url, timeoutMs = 6000) {
	const controller = new AbortController()
	const timer = setTimeout(() => controller.abort(), timeoutMs)
	try {
		const response = await fetch(url, {
			headers: {
				"User-Agent": "Mozilla/5.0",
				"Accept-Language": "zh-CN,zh;q=0.9",
			},
			signal: controller.signal,
		})
		if (!response.ok) return ""
		return await response.text()
	} catch {
		return ""
	} finally {
		clearTimeout(timer)
	}
}

function cleanHtmlText(html) {
	return String(html || "")
		.replace(/<script[\s\S]*?<\/script>/gi, " ")
		.replace(/<style[\s\S]*?<\/style>/gi, " ")
		.replace(/<[^>]+>/g, " ")
		.replace(/&nbsp;|&#160;/g, " ")
		.replace(/&amp;/g, "&")
		.replace(/\s+/g, " ")
		.trim()
}

function decodeHtmlValue(value) {
	return String(value || "")
		.replace(/&amp;/g, "&")
		.replace(/&quot;/g, "\"")
		.replace(/&#39;/g, "'")
		.replace(/&lt;/g, "<")
		.replace(/&gt;/g, ">")
		.replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
}

function decodeBingRedirect(url) {
	try {
		const parsed = new URL(url)
		if (!/(^|\.)bing\.com$/.test(parsed.hostname)) return url
		const encoded = parsed.searchParams.get("u")
		if (!encoded) return ""
		const payload = encoded.startsWith("a1") ? encoded.slice(2) : encoded
		const decoded = Buffer.from(payload.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8")
		return /^https?:\/\//i.test(decoded) ? decoded : ""
	} catch {
		return ""
	}
}

function extractSearchResultLinks(html) {
	const links = []
	for (const match of String(html || "").matchAll(/<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi)) {
		const rawHref = decodeHtmlValue(match[1])
		const url = decodeBingRedirect(rawHref) || rawHref
		if (!/^https?:\/\//i.test(url)) continue
		links.push({ url, title: cleanHtmlText(match[2]) })
	}
	return links
}

function extractUrlsFromText(text) {
	const matches = String(text || "").match(/https?:\/\/[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]+/g) || []
	return unique(matches.map((url) => url.replace(/[.,;:!?，。；：！？、）)】]+$/g, "")))
}

function absoluteUrl(href, baseUrl) {
	if (!href || /^javascript:|^mailto:/i.test(href)) return ""
	try {
		return new URL(decodeHtmlValue(href), baseUrl).toString()
	} catch {
		return ""
	}
}

function extractPageLinks(html, baseUrl) {
	const links = []
	for (const match of String(html || "").matchAll(/<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi)) {
		const url = absoluteUrl(match[1], baseUrl)
		if (!url) continue
		const index = match.index || 0
		const nearbyHtml = String(html || "").slice(Math.max(0, index - 500), index + match[0].length + 300)
		links.push({ url, title: cleanHtmlText(match[2]), context: cleanHtmlText(nearbyHtml) })
	}
	return links
}

function hostOf(url) {
	try {
		return new URL(url).hostname.toLowerCase().replace(/^www\./, "")
	} catch {
		return ""
	}
}

function eduBaseHost(host) {
	const parts = String(host || "").split(".").filter(Boolean)
	const eduIndex = parts.lastIndexOf("edu")
	if (eduIndex > 0 && parts[eduIndex + 1] === "cn") {
		return parts.slice(eduIndex - 1).join(".")
	}
	return host
}

function unique(items) {
	return [...new Set(items.filter(Boolean))]
}

function deriveOfficialHosts(officialChannels = []) {
	const hosts = []
	for (const channel of officialChannels) {
		const url = channel?.url || ""
		if (!url || /bing\.com|yz\.chsi\.com\.cn/.test(url)) continue
		const host = hostOf(url)
		if (host) hosts.push(host, eduBaseHost(host))
	}
	return unique(hosts)
}

function extractChsiFslqSchCode(admissionDataChannels = []) {
	for (const channel of admissionDataChannels || []) {
		try {
			const url = channel?.url || ""
			if (!url.includes("/zsgs/wap/fslq/")) continue
			const parsed = new URL(url)
			const code = parsed.searchParams.get("schCode")
			if (code) return code
		} catch {}
	}
	return ""
}

function hasMetricSignal(text) {
	return /复试线|复试分数线|初试成绩.*要求|进入复试|拟录取|录取名单|复试名单|复试成绩|报录比|报考录取|报名录取|录取情况|报考统计|报名统计|报考人数|录取人数/.test(text)
}

function isAdministrativeAdmissionNotice(text) {
	return /党团组织|组织关系|调档函|通信地址|录取通知书|定向合同|就业协议|入学须知|档案|户口|邮寄地址/.test(text)
}

function isSpecialPlanNotice(text) {
	return /少数民族|骨干人才|退役大学生|士兵计划|单独考试|专项计划|推荐免试|推免|免试研究生/.test(text)
}

function isDoctoralOnlyNotice(text) {
	const value = String(text || "")
	return /博士研究生|博士生/.test(value) && !/硕士|硕士研究生|全国统考|全国统一招生/.test(value)
}

function hasSectionSignal(text) {
	return /招生信息|招生公告|硕士招生|硕士研究生|通知公告|复试专栏|信息公开|历年数据|研究生数据/.test(text)
}

function majorKeywords(major = "") {
	const value = String(major || "")
	const keywords = [value]
	if (/计算机|软件|人工智能|电子信息|网络空间|信息工程|数据科学/.test(value)) {
		keywords.push("计算机", "软件", "人工智能", "信息工程", "电子信息", "网络空间", "数据科学")
	}
	return unique(keywords.map((item) => item.trim()).filter((item) => item.length >= 2))
}

function isTrustedEvidenceUrl(url, context = "", officialHosts = []) {
	try {
		const parsed = new URL(url)
		const host = parsed.hostname.toLowerCase().replace(/^www\./, "")
		const value = `${url} ${context}`.toLowerCase()
		if (/(baidu|google|bing|sogou|so\.com|kaoyan|yanshuoshi|eduour|wendu|jingc|eol\.cn|sohu|163\.com|qq\.com|zhihu|wikipedia)/i.test(value)) return false
		if (/\.(png|jpe?g|gif|webp|svg|ico|css|js|zip|rar|7z)(\?|$)/i.test(parsed.pathname)) return false
		if (host === "yz.chsi.com.cn") return /\/zsgs\/|\/sch\/|\/wap\/sch\//.test(parsed.pathname)
		if (officialHosts.some((officialHost) => host === officialHost || host.endsWith(`.${officialHost}`))) return true
		if ((host.endsWith(".edu.cn") || host.endsWith(".edu") || host.endsWith(".ac.cn")) && hasMetricSignal(context)) return true
		return false
	} catch {
		return false
	}
}

function classifyEvidence(text) {
	if (/报录比|报考录取|报名录取|录取情况|报考统计|报名统计|报考人数|录取人数/.test(text)) return "applicationRatio"
	if (/复试线|复试分数线|初试成绩.*要求|进入复试/.test(text)) return "retestLine"
	if (/拟录取|录取名单|复试名单|复试成绩/.test(text)) return "admissionList"
	return "officialNotice"
}

function typeLabel(type) {
	return {
		applicationRatio: "报录比/报考录取",
		retestLine: "复试线",
		admissionList: "拟录取/复试名单",
		officialNotice: "官方公告",
	}[type] || "官方公告"
}

function extractYear(text) {
	const years = String(text || "").match(/20(?:2[0-9]|1[8-9])/g) || []
	return years[0] || ""
}

function pickNumberNear(text, patterns, lower, upper) {
	for (const pattern of patterns) {
		const regex = new RegExp(`${pattern}[\\s\\S]{0,80}?([2-4]\\d{2})`, "g")
		for (const match of String(text || "").matchAll(regex)) {
			const value = Number(match[1])
			if (value >= lower && value <= upper) return value
		}
	}
	return null
}

function extractMetricNumber(text, labels, maxDigits = 5) {
	const labelPattern = labels.join("|")
	const regex = new RegExp(`(?:${labelPattern})[^0-9]{0,20}(\\d{1,${maxDigits}})`, "g")
	for (const match of String(text || "").matchAll(regex)) {
		const value = Number(match[1])
		if (Number.isFinite(value) && value > 0) return value
	}
	return null
}

function extractRatio(text) {
	const value = String(text || "")
	const direct = value.match(/报录比[^0-9]{0,30}(\d{1,2}(?:\.\d+)?)\s*[:：]\s*1/)
		|| value.match(/(\d{1,2}(?:\.\d+)?)\s*[:：]\s*1[^。；，,]{0,20}报录比/)
	if (direct) return Number(Number(direct[1]).toFixed(1))
	return null
}

function extractMetrics(text, { title = "", url = "", major = "" } = {}) {
	const combined = `${title} ${text}`
	const majorIndex = major ? combined.indexOf(major) : -1
	const focused = majorIndex >= 0 ? combined.slice(Math.max(0, majorIndex - 500), majorIndex + 1200) : combined
	const cutScore = pickNumberNear(focused, ["复试线", "复试分数线", "初试成绩[^。；，,]{0,20}要求", "进入复试[^。；，,]{0,20}成绩", "总分"], 240, 430)
	let ratio = extractRatio(focused)
	const applicants = extractMetricNumber(focused, ["报考人数", "报名人数", "一志愿报考人数"], 5)
	const admitted = extractMetricNumber(focused, ["录取人数", "拟录取人数", "统考录取人数"], 4)
	if (!ratio && applicants && admitted) ratio = Number((applicants / Math.max(1, admitted)).toFixed(1))
	const year = extractYear(title) || extractYear(url) || extractYear(focused)
	const metrics = { year }
	if (cutScore) metrics.cutScore = cutScore
	if (applicants) metrics.applicants = applicants
	if (admitted) metrics.admitted = admitted
	if (ratio) metrics.ratio = ratio
	return metrics
}

function metricText(metrics = {}) {
	const parts = []
	if (metrics.year) parts.push(`${metrics.year}年`)
	if (metrics.cutScore) parts.push(`复试线 ${metrics.cutScore}`)
	if (metrics.applicants) parts.push(`报考 ${metrics.applicants}`)
	if (metrics.admitted) parts.push(`录取 ${metrics.admitted}`)
	if (metrics.ratio) parts.push(`报录比 ${metrics.ratio}:1`)
	return parts.join("，")
}

function contextualLinkTitle(link, fallbackTitle = "") {
	const rawTitle = String(link?.title || "").trim()
	if (rawTitle && !/^(点击查看|查看|详情|全文|进入)$/.test(rawTitle)) return rawTitle
	const context = String(link?.context || "")
	const unitMatch = context.match(/([\u4e00-\u9fa5A-Za-z0-9、·]{2,40}(?:学院|学部|中心|实验室|研究院)(?:（[\u4e00-\u9fa5A-Za-z0-9、·]{2,30}）)?)/)
	if (unitMatch) {
		const suffix = /复试办法/.test(`${context} ${fallbackTitle}`) ? "复试办法" : "相关公告"
		return `${unitMatch[1]}${suffix}`
	}
	return rawTitle || fallbackTitle
}

function buildSearchSpecs({ school, major, majorCode, officialHosts }) {
	const core = [school, major, majorCode].filter(Boolean)
	const hosts = officialHosts.length ? officialHosts.slice(0, 3) : [""]
	const specs = []
	for (const host of hosts) {
		const site = host ? [`site:${host}`] : [school, "研究生招生网"]
		specs.push({ type: "retestLine", query: [...site, ...core, "复试线 进入复试 初试成绩要求"] })
		specs.push({ type: "applicationRatio", query: [...site, ...core, "报录比 报考录取情况 报考人数 录取人数"] })
		specs.push({ type: "admissionList", query: [...site, ...core, "拟录取名单 复试名单 复试成绩"] })
	}
	return specs.slice(0, 9)
}

async function crawlOfficialEvidenceCandidates(officialChannels = [], officialHosts = []) {
	const startUrls = unique((officialChannels || [])
		.map((channel) => channel?.url || "")
		.filter((url) => url && !/bing\.com|yz\.chsi\.com\.cn/.test(url)))
		.slice(0, 3)
	const candidates = []
	const seen = new Set()
	const sectionUrls = []

	const collectLinks = (links, sourceLabel = "学校官网/招生网") => {
		for (const link of links) {
			const context = `${link.title} ${link.url}`
			if (!isTrustedEvidenceUrl(link.url, context, officialHosts)) continue
			if (isAdministrativeAdmissionNotice(context)) continue
			const key = link.url.split("#")[0]
			if (hasMetricSignal(context)) {
				if (!seen.has(key)) {
					seen.add(key)
					candidates.push({
						...link,
						queryType: classifyEvidence(context),
						trusted: true,
						sourceLabel,
					})
				}
			} else if (hasSectionSignal(context) && sectionUrls.length < 8 && !seen.has(`section:${key}`)) {
				seen.add(`section:${key}`)
				sectionUrls.push(link.url)
			}
		}
	}

	for (const url of startUrls) {
		const html = await fetchText(url, 6000)
		if (!html) continue
		collectLinks(extractPageLinks(html, url))
	}

	for (const url of sectionUrls.slice(0, 5)) {
		const html = await fetchText(url, 6000)
		if (!html) continue
		collectLinks(extractPageLinks(html, url))
		if (candidates.length >= 10) break
	}

	return candidates.slice(0, 10)
}

async function fetchChsiFslqDetailCandidates({ school, major, admissionDataChannels = [], officialHosts = [] }) {
	const schCode = extractChsiFslqSchCode(admissionDataChannels)
	if (!schCode) return []
	const listUrl = `https://yz.chsi.com.cn/zsgs/wap/fslq/querydetailall?schCode=${encodeURIComponent(schCode)}`
	let data = null
	try {
		const response = await fetch(listUrl, {
			headers: {
				"User-Agent": "Mozilla/5.0",
				"Accept-Language": "zh-CN,zh;q=0.9",
				"X-Requested-With": "XMLHttpRequest",
				"Referer": `https://yz.chsi.com.cn/zsgs/wap/fslq/detailindex?schCode=${encodeURIComponent(schCode)}`,
			},
		})
		if (!response.ok) return []
		data = await response.json()
	} catch {
		return []
	}
	if (!data?.flag) return []

	const keywords = majorKeywords(major)
	const allItems = [
		...(data.msg?.yxsList || []).map((item) => ({ ...item, scope: "院系" })),
		...(data.msg?.schList || []).map((item) => ({ ...item, scope: "学校" })),
	]
	const scoreItem = (item) => {
		const text = `${item.title || ""} ${item.dicName || ""} ${item.yxsDicCode || ""}`
		let score = item.scope === "学校" ? 20 : 0
		if (hasMetricSignal(text)) score += 30
		if (/复试办法|复试及录取办法|复试录取办法|拟录取|复试名单/.test(text)) score += 40
		if (keywords.some((keyword) => text.includes(keyword))) score += 100
		return score
	}
	const selected = allItems
		.map((item) => ({ ...item, score: scoreItem(item) }))
		.filter((item) => item.score >= 50)
		.sort((a, b) => b.score - a.score)
		.slice(0, 8)

	const candidates = []
	for (const item of selected) {
		const detailPage = `https://yz.chsi.com.cn/zsgs/wap/fslq/detail?zsgsId=${encodeURIComponent(item.id)}&schCode=${encodeURIComponent(schCode)}`
		const apiUrl = `https://yz.chsi.com.cn/zsgs/wap/fslq/querydetail?zsgsId=${encodeURIComponent(item.id)}&schCode=${encodeURIComponent(schCode)}`
		let detail = null
		try {
			const response = await fetch(apiUrl, {
				headers: {
					"User-Agent": "Mozilla/5.0",
					"Accept-Language": "zh-CN,zh;q=0.9",
					"X-Requested-With": "XMLHttpRequest",
					"Referer": detailPage,
				},
			})
			if (response.ok) detail = await response.json()
		} catch {}
		const contentHtml = detail?.msg?.content || ""
		const contentText = cleanHtmlText(contentHtml)
		const title = detail?.msg?.title || item.title || "研招网复试录取详情"
		const context = `${title} ${contentText}`
		candidates.push({
			url: detailPage,
			title,
			queryType: classifyEvidence(context),
			trusted: true,
			sourceLabel: item.scope === "院系" ? "研招网院系复试录取信息" : "研招网学校复试录取信息",
		})
		const htmlLinks = extractPageLinks(contentHtml, detailPage)
		const textLinks = extractUrlsFromText(contentText).map((url) => ({ url, title }))
		for (const link of [...htmlLinks, ...textLinks]) {
			const linkContext = `${link.title || title} ${contentText}`
			if (!isTrustedEvidenceUrl(link.url, linkContext, officialHosts)) continue
			candidates.push({
				url: link.url,
				title: link.title || title,
				queryType: classifyEvidence(linkContext),
				trusted: true,
				sourceLabel: "研招网披露的学校/学院官网链接",
			})
		}
	}
	const seen = new Set()
	return candidates.filter((candidate) => {
		const key = candidate.url.split("#")[0]
		if (seen.has(key)) return false
		seen.add(key)
		return true
	}).slice(0, 10)
}

function confidenceForEvidence({ trusted, metrics, type }) {
	const hasConcreteMetric = !!(metrics?.cutScore || metrics?.ratio || metrics?.applicants || metrics?.admitted)
	if (trusted && hasConcreteMetric && (type === "retestLine" || type === "applicationRatio")) return "medium"
	if (trusted) return "source_only"
	return "low"
}

export async function findAdmissionEvidence(school, major, options = {}) {
	const majorCode = String(options.majorCode || "").trim()
	const cacheKey = JSON.stringify({ school, major, majorCode, official: options.officialChannels })
	if (evidenceCache.has(cacheKey)) return evidenceCache.get(cacheKey)

	const officialHosts = deriveOfficialHosts(options.officialChannels || [])
	const candidates = []
	const seen = new Set()
	for (const candidate of await crawlOfficialEvidenceCandidates(options.officialChannels || [], officialHosts)) {
		const key = candidate.url.split("#")[0]
		if (seen.has(key)) continue
		seen.add(key)
		candidates.push(candidate)
	}
	for (const candidate of await fetchChsiFslqDetailCandidates({ school, major, admissionDataChannels: options.admissionDataChannels || [], officialHosts })) {
		const key = candidate.url.split("#")[0]
		if (seen.has(key)) continue
		seen.add(key)
		candidates.push(candidate)
	}
	for (const spec of buildSearchSpecs({ school, major, majorCode, officialHosts })) {
		const html = await fetchText(buildBingSearchUrl(spec.query))
		const links = extractSearchResultLinks(html)
		for (const link of links.slice(0, 8)) {
			const context = `${link.title} ${spec.query.join(" ")}`
			const trusted = isTrustedEvidenceUrl(link.url, context, officialHosts)
			if (!trusted) continue
			if (isAdministrativeAdmissionNotice(context)) continue
			const key = link.url.split("#")[0]
			if (seen.has(key)) continue
			seen.add(key)
			candidates.push({ ...link, queryType: spec.type, trusted })
			if (candidates.length >= 10) break
		}
		if (candidates.length >= 10) break
	}

	const directChannels = (options.admissionDataChannels || [])
		.filter((channel) => /研招网/.test(channel?.label || "") && channel?.url)
		.map((channel) => ({
			url: channel.url,
			title: channel.label,
			queryType: "officialNotice",
			trusted: true,
			sourceLabel: "研招网",
			skipFetch: true,
		}))

	const enrichedRaw = await Promise.all([...candidates, ...directChannels].slice(0, 12).map(async (candidate) => {
		const url = candidate.url
		const title = candidate.title || url
		const type = candidate.queryType && candidate.queryType !== "officialNotice"
			? candidate.queryType
			: classifyEvidence(`${title} ${candidate.queryType}`)
		const isPdf = /\.pdf(\?|$)/i.test(url)
		const pageHtml = candidate.skipFetch || isPdf ? "" : await fetchText(url, 5000)
		const pageText = pageHtml ? cleanHtmlText(pageHtml) : ""
		const pageTitle = pageHtml.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]
		const metrics = extractMetrics(pageText || title, { title: cleanHtmlText(pageTitle || title), url, major })
		const confidence = confidenceForEvidence({ trusted: candidate.trusted, metrics, type })
		const attachments = pageHtml ? extractPageLinks(pageHtml, url)
			.filter((link) => /\.(pdf|xls|xlsx|csv)(\?|$)/i.test(link.url) && hasMetricSignal(`${link.title} ${link.url}`))
			.slice(0, 3)
			.map((link) => {
				const attachmentType = classifyEvidence(`${link.title} ${type}`)
				const attachmentMetrics = extractMetrics(link.title, { title: link.title, url: link.url, major })
				return {
					type: attachmentType,
					typeLabel: typeLabel(attachmentType),
					title: link.title || title,
					url: link.url,
					host: hostOf(link.url),
					sourceLabel: candidate.sourceLabel || "学校官网/招生网",
					confidence: "source_only",
					metrics: attachmentMetrics,
					metricText: metricText(attachmentMetrics),
					note: "官方统计附件已找到，当前仅展示链接，不自动解析PDF/表格",
				}
			}) : []
		const keywords = majorKeywords(major)
		const childLinks = pageHtml ? extractPageLinks(pageHtml, url)
			.filter((link) => !/\.(pdf|xls|xlsx|csv|png|jpe?g|gif|webp|svg|zip|rar)(\?|$)/i.test(link.url))
			.map((link) => {
				const linkSignal = `${link.title} ${link.url} ${link.context || ""}`
				const linkContext = `${linkSignal} ${pageText}`
				let score = hasMetricSignal(linkSignal) ? 30 : 0
				if (keywords.some((keyword) => linkSignal.includes(keyword))) score += 80
				if (/复试办法|复试录取|复试线|拟录取|复试名单|报录比/.test(linkSignal)) score += 30
				return { ...link, score, linkSignal, linkContext }
			})
			.filter((link) => link.score >= 60 && isTrustedEvidenceUrl(link.url, link.linkContext, officialHosts))
			.sort((a, b) => b.score - a.score)
			.slice(0, 3)
			.map((link) => {
				const displayTitle = contextualLinkTitle(link, title)
				const childType = classifyEvidence(link.linkSignal)
				const childMetrics = extractMetrics(displayTitle, { title: displayTitle, url: link.url, major })
				return {
					type: childType,
					typeLabel: typeLabel(childType),
					title: displayTitle,
					url: link.url,
					host: hostOf(link.url),
					sourceLabel: "来源页面内具体链接",
					confidence: "source_only",
					metrics: childMetrics,
					metricText: metricText(childMetrics),
					note: "从官方汇总页继续定位到的学院/专业相关页面",
				}
			}) : []
		return {
			type,
			typeLabel: typeLabel(type),
			title: cleanHtmlText(pageTitle || title) || title,
			url,
			host: hostOf(url),
			sourceLabel: candidate.sourceLabel || "学校官网/招生网",
			confidence,
			metrics,
			metricText: metricText(metrics),
			note: isPdf ? "PDF来源已找到，当前仅展示链接，不自动解析PDF表格" : (pageText ? "已抓取页面并尝试提取指标" : "已找到来源链接，页面内容未自动提取"),
			attachments,
			childLinks,
		}
	}))

	const enriched = enrichedRaw.flatMap((item) => {
		const { attachments = [], childLinks = [], ...rest } = item
		return [rest, ...attachments, ...childLinks]
	})
	const seenEvidence = new Set()
	const evidence = enriched
		.filter((item) => !isAdministrativeAdmissionNotice(`${item.title} ${item.url}`))
		.filter((item) => !isSpecialPlanNotice(`${item.title} ${item.url}`))
		.filter((item) => !isDoctoralOnlyNotice(`${item.title} ${item.url}`))
		.filter((item) => {
			const titleKey = String(item.title || "").replace(/\s+/g, "")
			const key = `${item.type}:${titleKey || item.url}`
			if (seenEvidence.has(key)) return false
			seenEvidence.add(key)
			return true
		})
		.slice(0, 8)
	const result = {
		evidence,
		summary: summarizeAdmissionEvidence(evidence),
	}
	evidenceCache.set(cacheKey, result)
	return result
}

export function buildHistoryFromAdmissionEvidence(evidence = []) {
	const byYear = new Map()
	for (const item of evidence) {
		const metrics = item.metrics || {}
		if (!metrics.year) continue
		if (!byYear.has(metrics.year)) byYear.set(metrics.year, { year: metrics.year, sources: [] })
		const row = byYear.get(metrics.year)
		if (metrics.cutScore) row.cutScore = metrics.cutScore
		if (metrics.applicants) row.applicants = metrics.applicants
		if (metrics.admitted) row.admitted = metrics.admitted
		if (metrics.ratio) row.ratio = metrics.ratio
		row.sources.push(item.url)
	}
	return [...byYear.values()]
		.map((row) => {
			if (!row.ratio && row.applicants && row.admitted) row.ratio = Number((row.applicants / Math.max(1, row.admitted)).toFixed(1))
			if (!row.applicants && row.ratio && row.admitted) row.applicants = Math.round(row.ratio * row.admitted)
			if (!row.admitted && row.ratio && row.applicants) row.admitted = Math.round(row.applicants / row.ratio)
			return row
		})
		.filter((row) => row.cutScore && row.applicants && row.admitted && row.ratio)
		.sort((a, b) => Number(a.year) - Number(b.year))
		.map((row) => ({
			year: row.year,
			applicants: row.applicants,
			admitted: row.admitted,
			ratio: Number(row.ratio.toFixed ? row.ratio.toFixed(1) : Number(row.ratio).toFixed(1)),
			cutScore: row.cutScore,
			note: "官网页面自动提取，需人工复核",
			sources: row.sources,
		}))
}

export function summarizeAdmissionEvidence(evidence = []) {
	const concrete = evidence.filter((item) => item.metrics?.cutScore || item.metrics?.ratio || item.metrics?.applicants || item.metrics?.admitted)
	const ratioSources = evidence.filter((item) => item.type === "applicationRatio")
	const cutScoreSources = evidence.filter((item) => item.type === "retestLine")
	const listSources = evidence.filter((item) => item.type === "admissionList")
	const warnings = []
	if (!evidence.length) warnings.push("未自动发现学校官网或研招网中的复试线、报录比、拟录取名单页面。")
	if (evidence.length && !concrete.length) warnings.push("已找到官方来源页面，但未能稳定提取连续年份的数字，预测可信度不足。")
	if (!ratioSources.length) warnings.push("未找到可核验的报录比/报考录取统计页面。")
	if (!cutScoreSources.length) warnings.push("未找到可核验的复试线页面。")
	return {
		total: evidence.length,
		concrete: concrete.length,
		ratioSources: ratioSources.length,
		cutScoreSources: cutScoreSources.length,
		listSources: listSources.length,
		warnings,
	}
}
