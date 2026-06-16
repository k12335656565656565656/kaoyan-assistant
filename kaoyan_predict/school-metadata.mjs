// School-level and official-channel metadata for postgraduate admissions.
// Lists are based on CHSI/MOE public pages; keep this module deterministic so
// the UI does not show "未确认" for stable school-level facts.

function normalizeSchoolName(name) {
	return String(name || "")
		.replace(/[（(]\s*北京\s*[）)]/g, "北京")
		.replace(/[（(]\s*华东\s*[）)]/g, "华东")
		.replace(/[（(]\s*武汉\s*[）)]/g, "武汉")
		.replace(/[（(].*?[）)]/g, "")
		.replace(/\s+/g, "")
		.replace(/学院$/, "学院")
		.trim()
}

function schoolAliases(school) {
	const normalized = normalizeSchoolName(school)
	const withoutBrackets = normalizeSchoolName(String(school || "").replace(/[（(].*?[）)]/g, ""))
	return [...new Set([normalized, withoutBrackets].filter((item) => item.length >= 4))]
}

function hasTargetSchoolSignal(school, context = "") {
	const normalizedContext = normalizeSchoolName(context)
	return schoolAliases(school).some((alias) => normalizedContext.includes(alias))
}

function toSet(text) {
	return new Set(text.split(/\s+/).map((item) => normalizeSchoolName(item)).filter(Boolean))
}

const PROJECT_985 = toSet(`
北京大学 清华大学 中国人民大学 北京航空航天大学 北京理工大学 中国农业大学 北京师范大学 中央民族大学
南开大学 天津大学 大连理工大学 东北大学 吉林大学 哈尔滨工业大学 复旦大学 同济大学 上海交通大学 华东师范大学
南京大学 东南大学 浙江大学 中国科学技术大学 厦门大学 山东大学 中国海洋大学 武汉大学 华中科技大学
湖南大学 中南大学 国防科技大学 中山大学 华南理工大学 四川大学 重庆大学 电子科技大学 西安交通大学
西北工业大学 西北农林科技大学 兰州大学
`)

const PROJECT_211 = toSet(`
北京大学 清华大学 中国人民大学 北京交通大学 北京工业大学 北京航空航天大学 北京理工大学 北京科技大学
北京化工大学 北京邮电大学 中国农业大学 北京林业大学 北京中医药大学 北京师范大学 北京外国语大学 中国传媒大学
中央财经大学 对外经济贸易大学 北京体育大学 中央音乐学院 中央民族大学 中国政法大学 华北电力大学
中国矿业大学 中国矿业大学北京 中国石油大学 中国石油大学北京 中国石油大学华东 中国地质大学 中国地质大学北京 中国地质大学武汉
南开大学 天津大学 天津医科大学 河北工业大学 太原理工大学 内蒙古大学 辽宁大学 大连理工大学 东北大学 大连海事大学
吉林大学 延边大学 东北师范大学 哈尔滨工业大学 哈尔滨工程大学 东北农业大学 东北林业大学
复旦大学 同济大学 上海交通大学 华东理工大学 东华大学 华东师范大学 上海外国语大学 上海财经大学 上海大学
海军军医大学 第二军医大学 南京大学 苏州大学 东南大学 南京航空航天大学 南京理工大学 河海大学 江南大学
南京农业大学 中国药科大学 南京师范大学 浙江大学 安徽大学 中国科学技术大学 合肥工业大学 厦门大学 福州大学 南昌大学
山东大学 中国海洋大学 郑州大学 武汉大学 华中科技大学 武汉理工大学 华中农业大学 华中师范大学 中南财经政法大学
湖南大学 中南大学 湖南师范大学 国防科技大学 中山大学 暨南大学 华南理工大学 华南师范大学 广西大学 海南大学
四川大学 重庆大学 西南大学 西南交通大学 电子科技大学 四川农业大学 西南财经大学 贵州大学 云南大学 西藏大学
西北大学 西安交通大学 西北工业大学 西安电子科技大学 长安大学 西北农林科技大学 陕西师范大学 空军军医大学 第四军医大学
兰州大学 青海大学 宁夏大学 新疆大学 石河子大学
`)

// Non-985/211 schools in the second-round Double First-Class list. 985/211
// schools are classified before this set, so they do not need to be repeated.
const DOUBLE_FIRST_CLASS_EXTRA = toSet(`
北京协和医学院 首都师范大学 外交学院 中国人民公安大学 中国音乐学院 中央美术学院 中央戏剧学院 中国科学院大学
天津工业大学 天津中医药大学 山西大学 上海海洋大学 上海中医药大学 上海体育大学 上海音乐学院 上海科技大学
南京邮电大学 南京林业大学 南京信息工程大学 南京医科大学 南京中医药大学 中国美术学院 宁波大学 河南大学
湘潭大学 华南农业大学 广州医科大学 广州中医药大学 南方科技大学 西南石油大学 成都理工大学 成都中医药大学
`)

const KNOWN_GRADUATE_ADMISSION_URLS = new Map(Object.entries({
	"南京大学": "https://yzb.nju.edu.cn/47863/list.htm",
	"上海海事大学": "https://yz.shmtu.edu.cn/8920/list.htm",
	"中国矿业大学": "https://yz.cumt.edu.cn/",
	"中国矿业大学北京": "https://yz.cumtb.edu.cn/",
	"中国农业大学": "https://yz.cau.edu.cn/",
	"中国石油大学北京": "https://grs.cup.edu.cn/d02/index.jhtml",
	"北京工业大学": "https://yanzhao.bjut.edu.cn/",
	"北京林业大学": "https://graduate.bjfu.edu.cn/zsgl/zsdt/index.html",
	"北京外国语大学": "https://graduate.bfsu.edu.cn/",
	"北京体育大学": "https://zs.bsu.edu.cn/yjszsw/",
	"中国传媒大学": "https://yz.cuc.edu.cn/",
	"中国地质大学北京": "https://bm.cugb.edu.cn/yjsyzsb/",
	"中国科学院大学": "https://admission.ucas.edu.cn/",
	"中国科学院物理研究所": "https://edu.iphy.ac.cn/",
	"中国科学院高能物理研究所": "https://www.ihep.cas.cn/zszp/zsxx/",
	"中国科学院理论物理研究所": "https://itp.cas.cn/yjs/",
	"中国科学院计算技术研究所": "https://ict.cas.cn/yjsjy/zsxx/",
	"中国科学院微电子研究所": "https://www.ime.cas.cn/kjrh/ssszs/",
	"中国工程物理研究院": "https://zsxx.gscaep.ac.cn/",
	"中国空间技术研究院(航天五院)": "https://www.cast.cn/3g/news/7507",
	"中国空间技术研究院": "https://www.cast.cn/3g/news/7507",
	"北京工商大学": "https://yzb.btbu.edu.cn/",
	"国际关系学院": "https://yjszs.uir.cn/",
	"首都师范大学": "https://grad.cnu.edu.cn/",
	"北京联合大学": "https://graduate.buu.edu.cn/col/col30688/index.html",
	"天津医科大学": "https://gs.tmu.edu.cn/3110/list.htm",
	"天津城建大学": "https://master.tcu.edu.cn/zsgz.htm",
	"河北经贸大学": "https://yjs.hueb.edu.cn/",
	"内蒙古民族大学": "https://yjsy.imun.edu.cn/list/3",
	"北京交通大学": "https://yzb.bjtu.edu.cn/",
	"华北电力大学": "https://yjsy.ncepu.edu.cn/zsxx/sszsxx/index.htm",
	"西南交通大学": "https://yz.swjtu.edu.cn/",
	"南方科技大学": "https://gs.sustech.edu.cn/#/admission/index",
	"清华大学": "https://yz.tsinghua.edu.cn/",
	"北京大学": "https://admission.pku.edu.cn/zsxx/sszs/",
	"中国人民大学": "https://pgs.ruc.edu.cn/",
	"北京航空航天大学": "https://yzb.buaa.edu.cn/",
	"北京理工大学": "https://grd.bit.edu.cn/zsgz/ssyjs/index.htm",
	"北京师范大学": "https://yz.bnu.edu.cn/",
	"南京航空航天大学": "https://www.graduate.nuaa.edu.cn/zsgz/list.htm",
	"南京农业大学": "https://zsgz.njau.edu.cn/",
	"南京理工大学": "https://gs.njust.edu.cn/zsw/",
	"南京信息工程大学": "https://yzb.nuist.edu.cn/",
	"苏州大学": "https://yjs.suda.edu.cn/",
	"合肥工业大学": "https://yjszs.hfut.edu.cn/",
	"上海大学": "https://yjszs.shu.edu.cn/",
	"华东理工大学": "https://gschool.ecust.edu.cn/",
	"东华大学": "https://yjszs.dhu.edu.cn/",
	"西安电子科技大学": "https://gr.xidian.edu.cn/yjsy/yjszs.htm",
	"武汉理工大学": "https://gd.whut.edu.cn/zs/",
	"华中师范大学": "https://gs.ccnu.edu.cn/",
	"郑州大学": "https://gs.zzu.edu.cn/",
	"南昌大学": "https://yjsy.ncu.edu.cn/",
	"杭州电子科技大学": "https://grs.hdu.edu.cn/",
	"深圳大学": "https://yz.szu.edu.cn/",
	"华南农业大学": "https://yzb.scau.edu.cn/",
	"青岛大学": "https://grad.qdu.edu.cn/",
	"山东科技大学": "https://yjsy.sdust.edu.cn/zhaosheng/",
	"河南师范大学": "https://www.htu.edu.cn/yjszsw/",
	"河南大学": "https://grs.henu.edu.cn/",
	"江苏大学": "https://yz.ujs.edu.cn/",
	"扬州大学": "https://yjszs.yzu.edu.cn/",
	"宁波大学": "https://graduate.nbu.edu.cn/",
	"湘潭大学": "https://yjsc.xtu.edu.cn/",
	"昆明理工大学": "https://yjs.kmust.edu.cn/",
	"重庆邮电大学": "https://yjs.cqupt.edu.cn/",
	"桂林电子科技大学": "https://www.guet.edu.cn/gra/",
	"成都信息工程大学": "https://yjsc.cuit.edu.cn/",
	"南开大学": "https://yzb.nankai.edu.cn/",
	"天津大学": "http://yzb.tju.edu.cn/",
	"大连理工大学": "https://gs.dlut.edu.cn/yjszs.htm",
	"东北大学": "http://yz.neu.edu.cn/",
	"吉林大学": "https://zsb.jlu.edu.cn/",
	"哈尔滨工业大学": "https://yzb.hit.edu.cn/",
	"复旦大学": "https://gsao.fudan.edu.cn/",
	"同济大学": "https://yz.tongji.edu.cn/",
	"上海交通大学": "https://yzb.sjtu.edu.cn/",
	"华东师范大学": "https://yjszs.ecnu.edu.cn/",
	"东南大学": "https://yzb.seu.edu.cn/",
	"浙江大学": "http://www.grs.zju.edu.cn/yjszs/",
	"中国科学技术大学": "https://yz.ustc.edu.cn/",
	"厦门大学": "https://zs.xmu.edu.cn/",
	"山东大学": "https://www.yz.sdu.edu.cn/",
	"武汉大学": "https://gs.whu.edu.cn/zsgz.htm",
	"华中科技大学": "http://gszs.hust.edu.cn/",
	"中山大学": "https://graduate.sysu.edu.cn/zsw/",
	"华南理工大学": "https://yz.scut.edu.cn/",
	"四川大学": "https://yz.scu.edu.cn/",
	"重庆大学": "https://yz.cqu.edu.cn/",
	"电子科技大学": "https://yz.uestc.edu.cn/",
	"西安交通大学": "https://yz.xjtu.edu.cn/",
	"西北工业大学": "https://yzb.nwpu.edu.cn/",
	"兰州大学": "https://yz.lzu.edu.cn/",
}))

const schoolRowCache = new Map()
const textCache = new Map()
const officialUrlCache = new Map()
const officialSearchCache = new Map()

function hasSchoolSpecificUrl(url) {
	if (!url) return false
	return !/yz\.chsi\.com\.cn/.test(url)
}

function buildChsiSchoolCatalogUrlFromRow(row) {
	if (!row?.dwdm || !row?.dwmc || !row?.schId || !row?.sign) return ""
	const params = new URLSearchParams()
	params.set("dwdm", row.dwdm)
	params.set("dwmc", row.dwmc)
	params.set("ssmc", row.szss || row.ssmc || "")
	params.set("schId", row.schId)
	params.set("xxfs", row.mxxfs || row.xxfs || "")
	params.set("mldm", row.mldm || "")

	const schoolTypes = []
	if (row.zhx === "1") schoolTypes.push("zhx")
	if (row.syl === "1") schoolTypes.push("syl")
	if (row.bs === "1") schoolTypes.push("bs")
	schoolTypes.forEach((type, index) => params.append(`dwlxs[${index}]`, type))

	params.set("tydxs", row.mtydxs || row.tydxs || "")
	params.set("jsggjh", row.mjsggjh || row.jsggjh || "")
	params.set("sign", row.sign)
	return `https://yz.chsi.com.cn/zsml/dwzy.do?${params.toString()}`
}

async function fetchChsiSchoolRow(school, schoolCode) {
	const cacheKey = `${schoolCode || ""}::${normalizeSchoolName(school)}`
	if (schoolRowCache.has(cacheKey)) return schoolRowCache.get(cacheKey)
	const body = new URLSearchParams()
	body.set("dwmc", String(school || "").replace(/（/g, "(").replace(/）/g, ")"))
	body.set("dwdm", schoolCode || "")
	body.set("ssdm", "")
	body.set("xxfs", "")
	body.append("dwlxs", "all")
	body.set("tydxs", "")
	body.set("jsggjh", "")
	body.set("start", "0")
	body.set("curPage", "1")
	body.set("pageSize", "20")

	const controller = new AbortController()
	const timer = setTimeout(() => controller.abort(), 5000)
	try {
		const response = await fetch("https://yz.chsi.com.cn/zsml/rs/dws.do", {
			method: "POST",
			headers: {
				"Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
				"X-Requested-With": "XMLHttpRequest",
				"Referer": "https://yz.chsi.com.cn/zsml/dw.do",
				"User-Agent": "Mozilla/5.0",
				"Accept-Language": "zh-CN,zh;q=0.9",
			},
			body,
			signal: controller.signal,
		})
		if (!response.ok) return ""
		const data = await response.json()
		const list = data?.msg?.list || []
		const normalizedSchool = normalizeSchoolName(school)
		const row = list.find((item) => schoolCode && String(item.dwdm) === String(schoolCode))
			|| list.find((item) => normalizeSchoolName(item.dwmc) === normalizedSchool)
			|| list.find((item) => hasTargetSchoolSignal(school, item.dwmc))
		schoolRowCache.set(cacheKey, row || null)
		return row || null
	} catch {
		schoolRowCache.set(cacheKey, null)
		return null
	} finally {
		clearTimeout(timer)
	}
}

async function fetchText(url, timeoutMs = 5000) {
	if (textCache.has(url)) return textCache.get(url)
	const controller = new AbortController()
	const timer = setTimeout(() => controller.abort(), timeoutMs)
	try {
		const response = await fetch(url, {
			headers: {
				"User-Agent": "Mozilla/5.0",
				"Accept-Language": "zh-CN,zh;q=0.9",
				"Referer": "https://yz.chsi.com.cn/",
			},
			signal: controller.signal,
		})
		if (!response.ok) return ""
		const text = await response.text()
		textCache.set(url, text)
		return text
	} catch {
		return ""
	} finally {
		clearTimeout(timer)
	}
}

function absoluteChsiUrl(url) {
	if (!url) return ""
	if (/^https?:\/\//i.test(url)) return url
	return `https://yz.chsi.com.cn${url.startsWith("/") ? "" : "/"}${url}`
}

function cleanHtmlText(html) {
	return String(html || "")
		.replace(/<script[\s\S]*?<\/script>/gi, " ")
		.replace(/<style[\s\S]*?<\/style>/gi, " ")
		.replace(/<[^>]+>/g, " ")
		.replace(/&nbsp;/g, " ")
		.replace(/&amp;/g, "&")
		.replace(/\s+/g, " ")
		.trim()
}

function isUsefulOfficialUrl(url, context = "") {
	try {
		if (!url || /\*{2,}/.test(url) || /^https?:\/\/\*+/i.test(url)) return false
		const parsed = new URL(url)
		const host = parsed.hostname.toLowerCase()
		if (/\.(pdf|xls|xlsx|doc|docx|png|jpe?g|gif|webp|svg|ico|css|js|zip|rar|7z)(\?|$)/i.test(parsed.pathname)) return false
		if (/(^|\.)chsi\.com\.cn$|(^|\.)chei\.com\.cn$|baidu\.com|google|bing\.com|beian|miit|gov\.cn|account\.chsi\.com\.cn/.test(host)) return false
		const value = `${url} ${context}`.toLowerCase()
		const hasAdmissionSignal = /招生网址|研究生招生网|研究生院|硕士招生|博士招生|招生信息|招生办公室|研招|招生专题/.test(context)
			|| /(^|[./-])(yz|yzb|yzxc|yjs|yjsy|gs|gsa|gsao|graduate|grs|admission|zsb|zsw)([./-]|$)|zsxx|sszs|zsgz/i.test(value)
		if (host.endsWith(".edu.cn") || host.endsWith(".edu") || host.endsWith(".ac.cn")) return hasAdmissionSignal
		return hasAdmissionSignal
	} catch {
		return false
	}
}

function isGenericSchoolHomeUrl(url) {
	try {
		const parsed = new URL(url)
		const value = `${parsed.hostname}${parsed.pathname}`.toLowerCase()
		const path = parsed.pathname.replace(/\/+/g, "/")
		if (/(^|[./-])(yz|yzb|yjs|yjsy|gs|graduate|grs|admission)([./-]|$)|zsxx|sszs|zsgz/i.test(value)) return false
		return /^\/?$/.test(path) || /^\/(index\.(html?|aspx?|php|jsp))?$/i.test(path)
	} catch {
		return false
	}
}

function rankOfficialUrl(url, context = "") {
	let score = 0
	const value = `${url} ${context}`.toLowerCase()
	if (/招生网址|研究生招生网|研招|招生办公室/.test(context)) score += 80
	if (/研究生院|研究生/.test(context)) score += 40
	if (/(^|[./-])(yz|yzb|yjs|yjsy|gs|graduate|grs|admission)([./-]|$)/i.test(value)) score += 50
	if (/\/$|index|list|招生|zhao|admission|graduate|yjs|yz/i.test(value)) score += 10
	if (/www\./i.test(value)) score -= 5
	return score
}

function extractOfficialAdmissionUrl(html) {
	const text = cleanHtmlText(html)
	const urls = [...new Set(String(html || "").match(/https?:\/\/[^\s"'<>，。；;）)】]+/g) || [])]
	const ranked = urls.map((url) => {
		const idx = text.indexOf(url)
		const context = idx >= 0 ? text.slice(Math.max(0, idx - 80), idx + url.length + 80) : ""
		return { url, context, score: rankOfficialUrl(url, context) }
	}).filter((item) => isUsefulOfficialUrl(item.url, item.context)).sort((a, b) => b.score - a.score)
	return ranked[0]?.url || ""
}

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
		links.push({ url, context: cleanHtmlText(match[2]) })
	}
	return links
}

function rankSearchOfficialUrl(url, context = "", school = "") {
	let score = rankOfficialUrl(url, context)
	const value = `${url} ${context}`.toLowerCase()
	if (school && context.includes(school)) score += 30
	if (/研究生招生网|研究生院|招生信息|硕士招生|研招|招生专题/.test(context)) score += 70
	if (/(^|[./-])(yz|yzb|yjs|yjsy|gs|graduate|grs|admission)([./-]|$)|zsxx|sszs|zsgz/i.test(value)) score += 50
	if (/本科|继续教育|在职|培训|考研|论坛/.test(context)) score -= 80
	if (/yanshuoshi|kaoyan|eduour|wendu|jingc|eol\.cn|sohu|163\.com|qq\.com|news/i.test(value)) score -= 120
	return score
}

async function searchOfficialAdmissionUrl(school) {
	const normalized = normalizeSchoolName(school)
	if (!normalized) return ""
	if (officialSearchCache.has(normalized)) return officialSearchCache.get(normalized)

	const candidates = []
	const queries = [
		[school, "研究生招生网"],
		[school, "研招网"],
		[school, "研究生院", "招生信息"],
	]
	for (const query of queries) {
		const html = await fetchText(buildBingSearchUrl(query), 6000)
		for (const link of extractSearchResultLinks(html)) {
			if (!hasTargetSchoolSignal(school, `${link.context} ${link.url}`)) continue
			if (!isUsefulOfficialUrl(link.url, link.context)) continue
			candidates.push({
				...link,
				score: rankSearchOfficialUrl(link.url, link.context, school),
			})
		}
		if (candidates.length) break
	}
	const result = candidates.sort((a, b) => b.score - a.score)[0]?.url || ""
	officialSearchCache.set(normalized, result)
	return result
}

async function fetchSchoolOfficialAdmissionUrl(row) {
	if (!row?.schId) return ""
	if (officialUrlCache.has(row.schId)) return officialUrlCache.get(row.schId)
	const infoUrl = `https://yz.chsi.com.cn/sch/schoolInfo--schId-${row.schId}.dhtml`
	const infoHtml = await fetchText(infoUrl)
	if (!infoHtml) return ""
	const contactHref = [...infoHtml.matchAll(/<a\b[^>]*href=['"]([^'"]+)['"][^>]*>([\s\S]*?)<\/a>/gi)]
		.map((match) => ({
			href: match[1],
			text: cleanHtmlText(match[2]),
		}))
		.find((link) => link.text.includes("联系办法"))?.href
	const contactHtml = contactHref ? await fetchText(absoluteChsiUrl(contactHref)) : infoHtml
	const url = extractOfficialAdmissionUrl(contactHtml || infoHtml)
	officialUrlCache.set(row.schId, url)
	return url
}

async function resolveOfficialAdmissionUrl(school, schoolRow, sourceUrl = "") {
	const knownUrl = KNOWN_GRADUATE_ADMISSION_URLS.get(normalizeSchoolName(school))
	const usefulSourceUrl = hasSchoolSpecificUrl(sourceUrl) && isUsefulOfficialUrl(sourceUrl, school) ? sourceUrl : ""
	if (knownUrl) return knownUrl
	const chsiOfficialUrl = await fetchSchoolOfficialAdmissionUrl(schoolRow)
	if (chsiOfficialUrl && !isGenericSchoolHomeUrl(chsiOfficialUrl)) return chsiOfficialUrl
	if (usefulSourceUrl) return usefulSourceUrl
	const searchedUrl = await searchOfficialAdmissionUrl(school)
	return searchedUrl || ""
}

export function resolveSchoolLevel(schoolName, fallbackLevel = "") {
	const normalized = normalizeSchoolName(schoolName)
	const fallback = String(fallbackLevel || "").trim()
	if (PROJECT_985.has(normalized)) {
		return {
			label: "985",
			tags: ["985", "211", "双一流"],
			confidence: "high",
			source: "本地权威名单：985工程/211工程/第二轮双一流",
		}
	}
	if (PROJECT_211.has(normalized)) {
		return {
			label: "211",
			tags: ["211", "双一流"],
			confidence: "high",
			source: "本地权威名单：211工程/第二轮双一流",
		}
	}
	if (DOUBLE_FIRST_CLASS_EXTRA.has(normalized)) {
		return {
			label: "双一流",
			tags: ["双一流"],
			confidence: "high",
			source: "本地权威名单：第二轮双一流",
		}
	}
	if (fallback && !["未知", "未确认", "相关学院"].includes(fallback)) {
		return {
			label: fallback,
			tags: [fallback],
			confidence: "medium",
			source: "招生目录/补充源附带层次字段",
		}
	}
	return {
		label: "双非",
		tags: ["双非"],
		confidence: "medium",
		source: "未命中985/211/第二轮双一流名单，按双非展示",
	}
}

function normalizeChannelArgs(schoolName, sourceUrl = "", options = {}) {
	if (schoolName && typeof schoolName === "object") {
		const input = schoolName
		const extraOptions = sourceUrl && typeof sourceUrl === "object" ? sourceUrl : options
		return {
			school: String(input.school || input.schoolName || input.name || "").trim(),
			sourceUrl: String(input.sourceUrl || input.url || "").trim(),
			options: { ...extraOptions, ...input },
		}
	}
	return {
		school: String(schoolName || "").trim(),
		sourceUrl: String(sourceUrl || "").trim(),
		options: options || {},
	}
}

export async function buildOfficialChannels(schoolName, sourceUrl = "", options = {}) {
	const args = normalizeChannelArgs(schoolName, sourceUrl, options)
	const school = args.school
	const schoolCode = String(args.options.schoolCode || args.options.dwdm || "").trim()
	const schoolRow = await fetchChsiSchoolRow(school, schoolCode)
	const channels = []
	const seen = new Set()
	const add = (label, url, note = "") => {
		if (!url || seen.has(url)) return
		seen.add(url)
		channels.push({ label, url, note })
	}

	const schoolSiteUrl = await resolveOfficialAdmissionUrl(school, schoolRow, args.sourceUrl)
	if (schoolSiteUrl) add("学校研究生官网/招生网", schoolSiteUrl, "招生单位官方信息入口")

	const catalogUrl = buildChsiSchoolCatalogUrlFromRow(schoolRow)
	add(
		catalogUrl ? "研招网对应院校招生目录" : "研招网招生单位查询",
		catalogUrl || "https://yz.chsi.com.cn/zsml/dw.do",
		catalogUrl ? `${school}在研招网的招生专业目录页` : "研招网官方招生单位查询入口",
	)
	return channels
}

export async function buildAdmissionDataChannels(schoolName, options = {}) {
	const args = normalizeChannelArgs(schoolName, "", options)
	const school = args.school
	const schoolCode = String(args.options.schoolCode || args.options.dwdm || "").trim()
	const major = String(args.options.major || "").trim()
	const majorCode = String(args.options.majorCode || "").trim()
	const schoolRow = await fetchChsiSchoolRow(school, schoolCode)
	const officialUrl = await resolveOfficialAdmissionUrl(school, schoolRow)
	const channels = []
	const seen = new Set()
	const add = (label, url, note = "") => {
		if (!url || seen.has(url)) return
		seen.add(url)
		channels.push({ label, url, note })
	}

	if (officialUrl) {
		try {
			const host = new URL(officialUrl).hostname
			add("学校官网检索录取数据", buildBingSearchUrl(["site:" + host, school, major, majorCode, "复试名单 拟录取名单 复试线 报录比"]), "定位复试名单、拟录取名单、复试线或报录比公告")
		} catch {
			add("学校官网检索录取数据", officialUrl, "在招生单位官网检索复试名单、拟录取名单、复试线或报录比公告")
		}
	} else {
		add("学校官网检索录取数据", buildBingSearchUrl([school, major, majorCode, "研究生招生网 复试名单 拟录取名单 复试线 报录比"]), "未抽取到学校官网时的录取数据检索入口")
	}

	const dwdm = schoolRow?.dwdm || schoolCode
	if (dwdm) {
		add("研招网复试录取信息", `https://yz.chsi.com.cn/zsgs/wap/fslq/detailindex?schCode=${encodeURIComponent(dwdm)}`, "研招网信息公开中的复试录取入口")
	}
	if (schoolRow?.schId) {
		add("研招网院校招生信息", `https://yz.chsi.com.cn/sch/schoolInfo--schId-${encodeURIComponent(schoolRow.schId)}.dhtml`, "招生简章、信息公告、录取规则、调剂办法等")
	}
	return channels
}
