// media-scraper.mjs — 8 平台真实媒体数据抓取（纯 Node.js ESM，零外部依赖）
// 每个平台返回 { score: 0-100, source: 'real'|'simulated', raw: {...} }
// 评分公式完整参考原 exam-forecast-system 预测系统

const DEFAULT_HEADERS = {
	"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
	"Accept": "application/json, text/plain, */*",
	"Accept-Language": "zh-CN,zh;q=0.9",
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)) }
function randDelay() { return sleep(300 + Math.random() * 700) }
function hashString(str) {
	let h = 0
	for (let i = 0; i < str.length; i++) { h = (h << 5) - h + str.charCodeAt(i); h |= 0 }
	return Math.abs(h)
}

// ===== B站 =====
async function fetchBilibili(keyword) {
	try {
		await randDelay()
		// 新版搜索API，不需要Cookie也能过
		const url = `https://api.bilibili.com/x/web-interface/wbi/search/all/v2?keyword=${encodeURIComponent(keyword)}`
		const res = await fetch(url, {
			headers: {
				...DEFAULT_HEADERS,
				"Origin": "https://search.bilibili.com",
				"Referer": "https://search.bilibili.com/",
			},
		})
		if (!res.ok) throw new Error(`HTTP ${res.status}`)
		const data = await res.json()
		if (data.code !== 0) throw new Error(`code ${data.code}`)

		// 提取视频类型的结果
		const videoResult = data.data?.result?.find(r => r.result_type === "video")
		const videos = videoResult?.data || []
		const now = Date.now() / 1000
		const thirtyDaysAgo = now - 30 * 86400
		const sevenDaysAgo = now - 7 * 86400

		let totalPlay = 0, totalDanmaku = 0, totalLike = 0
		let recent30 = 0, recent7 = 0
		for (const v of videos) {
			totalPlay += v.play || 0
			totalDanmaku += v.danmaku || 0
			totalLike += v.like || 0
			if (v.pubdate > thirtyDaysAgo) recent30++
			if (v.pubdate > sevenDaysAgo) recent7++
		}

		// 评分：播放分(40) + 近期分(30) + 互动分(30)
		const playScore = Math.min(40, Math.log10(Math.max(1, totalPlay)) * 8)
		const recentScore = Math.min(30, (recent30 / 3) * 5 + (recent7 / 1) * 3)
		const engagement = totalPlay > 0 ? (totalDanmaku + totalLike) / totalPlay : 0
		const interactScore = Math.min(30, engagement * 300)
		const score = Math.round(playScore + recentScore + interactScore)

		return {
			score: Math.min(100, score),
			source: "real",
			raw: { videoCount: videos.length, totalPlay, recent30, recent7, totalDanmaku, totalLike },
		}
	} catch (e) {
		return failedScore("bilibili", e.message)
	}
}

// ===== 知乎 =====
async function fetchZhihu(keyword) {
	try {
		await randDelay()
		const url = `https://www.zhihu.com/api/v4/search_v3?gk_version=zv-130&t=general&q=${encodeURIComponent(keyword)}`
		const res = await fetch(url, {
			headers: {
				...DEFAULT_HEADERS,
				"x-requested-with": "fetch",
				"Referer": `https://www.zhihu.com/search?type=content&q=${encodeURIComponent(keyword)}`,
			},
		})
		if (!res.ok) throw new Error(`HTTP ${res.status}`)
		const data = await res.json()
		const paging = data.paging || {}
		const totals = paging.totals || 0

		// 评分：关注分(50) + 内容分(50) — 搜索模式下用结果数近似
		const contentScore = Math.min(50, Math.log10(Math.max(1, totals)) * 8)
		const score = Math.round(contentScore * 2)

		return {
			score: Math.min(100, score),
			source: "real",
			raw: { totalResults: totals },
		}
	} catch (e) {
		return failedScore("zhihu", e.message)
	}
}

// ===== 百度 =====
async function fetchBaidu(keyword) {
	try {
		await randDelay()
		const url = `https://www.baidu.com/s?wd=${encodeURIComponent(keyword)}`
		const res = await fetch(url, { headers: { ...DEFAULT_HEADERS, "Accept": "text/html" } })
		if (!res.ok) throw new Error(`HTTP ${res.status}`)
		const html = await res.text()

		// 提取 "百度为您找到相关结果约 xxx 个"
		const match = html.match(/百度为您找到相关结果约?\s*([\d,]+)/)
		const count = match ? Number.parseInt(match[1].replace(/,/g, ""), 10) : 0

		// 评分：log10(count) * 12，封顶 100
		const score = Math.min(100, Math.log10(Math.max(1, count)) * 12)

		return {
			score: Math.round(score),
			source: "real",
			raw: { resultCount: count },
		}
	} catch (e) {
		return failedScore("baidu", e.message)
	}
}

// ===== 抖音 =====
async function fetchDouyin(keyword) {
	try {
		await randDelay()
		// 抖音搜索页反爬极严，尝试 fetch 后回退
		const url = `https://www.douyin.com/search/${encodeURIComponent(keyword)}?type=video`
		const res = await fetch(url, {
			headers: {
				...DEFAULT_HEADERS,
				"Accept": "text/html",
				"Referer": "https://www.douyin.com/",
			},
		})
		if (!res.ok) throw new Error(`HTTP ${res.status}`)
		const html = await res.text()

		// 尝试提取视频数量或播放数（抖音 HTML 结构多变，成功率低）
		let videoCount = 0
		const countMatch = html.match(/"count":\s*(\d+)/)
		if (countMatch) videoCount = Number.parseInt(countMatch[1], 10)

		if (videoCount === 0) throw new Error("no data")

		// 评分：播放(50) + 点赞(30) + 视频数(20) — 简化版
		const score = Math.min(100, Math.log10(Math.max(1, videoCount * 10000)) * 10)
		return {
			score: Math.round(score),
			source: "real",
			raw: { videoCount },
		}
	} catch (e) {
		return failedScore("douyin", e.message)
	}
}

// ===== 贴吧 =====
async function fetchTieba(keyword) {
	try {
		await randDelay()
		const kw = `${keyword.replace(/\s+/g, "")}吧`
		const url = `https://tieba.baidu.com/f?kw=${encodeURIComponent(kw)}`
		const res = await fetch(url, { headers: { ...DEFAULT_HEADERS, "Accept": "text/html" } })
		if (!res.ok) throw new Error(`HTTP ${res.status}`)
		const html = await res.text()

		// 提取关注人数和帖子数
		let members = 0, posts = 0
		const memMatch = html.match(/card_menNum[^>]*>([\d,]+)/) || html.match(/关注人数[:：\s]*([\d,]+)/) || html.match(/members[^>]*>([\d,]+)/)
		if (memMatch) members = Number.parseInt(memMatch[1].replace(/,/g, ""), 10)
		const postMatch = html.match(/card_infoNum[^>]*>([\d,]+)/) || html.match(/帖子数[:：\s]*([\d,]+)/) || html.match(/posts[^>]*>([\d,]+)/)
		if (postMatch) posts = Number.parseInt(postMatch[1].replace(/,/g, ""), 10)

		if (members === 0 && posts === 0) throw new Error("no data")

		// 评分：关注(30) + 帖子(25) + 活跃(15) + 互动(40)
		const memberScore = Math.min(30, Math.log10(Math.max(1, members)) * 9)
		const postScore = Math.min(25, Math.log10(Math.max(1, posts)) * 7)
		const activeScore = Math.min(15, Math.log10(Math.max(1, members * 0.05 + 1)) * 6)
		const score = Math.round(memberScore + postScore + activeScore + 15) // 互动分简化为固定15

		return {
			score: Math.min(100, score),
			source: "real",
			raw: { members, posts },
		}
	} catch (e) {
		return failedScore("tieba", e.message)
	}
}

// ===== 微信 =====
async function fetchWechat(keyword) {
	try {
		await randDelay()
		const url = `https://weixin.sogou.com/weixin?type=2&query=${encodeURIComponent(keyword)}`
		const res = await fetch(url, { headers: { ...DEFAULT_HEADERS, "Accept": "text/html" } })
		if (!res.ok) throw new Error(`HTTP ${res.status}`)
		const html = await res.text()

		// 提取结果数
		let count = 0
		const match = html.match(/找到约?\s*([\d,]+)\s*条结果/) || html.match(/(\d+)\s*条结果/)
		if (match) count = Number.parseInt(match[1].replace(/,/g, ""), 10)

		// 评分：搜狗文章数(60) + 固定巨量(40) — 简化版
		const sogouScore = Math.min(60, Math.log10(Math.max(1, count)) * 10)
		const score = Math.round(sogouScore + 20)

		return {
			score: Math.min(100, score),
			source: "real",
			raw: { sogouCount: count },
		}
	} catch (e) {
		return failedScore("wechat", e.message)
	}
}

// ===== 小红书 =====
async function fetchXiaohongshu(keyword) {
	try {
		await randDelay()
		const url = `https://www.xiaohongshu.com/search_result?keyword=${encodeURIComponent(keyword)}`
		const res = await fetch(url, {
			headers: {
				...DEFAULT_HEADERS,
				"Accept": "text/html",
				"Referer": "https://www.xiaohongshu.com/",
			},
		})
		if (!res.ok) throw new Error(`HTTP ${res.status}`)
		const html = await res.text()

		// 尝试从 __INITIAL_STATE__ 提取笔记数
		let noteCount = 0, totalLike = 0
		const stateMatch = html.match(/window\.__INITIAL_STATE__\s*=\s*({.+?});<\//)
		if (stateMatch) {
			try {
				const state = JSON.parse(stateMatch[1])
				const notes = state.search?.notes || state.searchResult?.notes || []
				noteCount = notes.length
				for (const n of notes) totalLike += n.likes || n.likeCount || 0
			} catch {}
		}

		if (noteCount === 0) {
			// 备选：正则匹配笔记数量
			const countMatch = html.match(/"total":\s*(\d+)/) || html.match(/([\d,]+)\s*篇笔记/)
			if (countMatch) noteCount = Number.parseInt(countMatch[1].replace(/,/g, ""), 10)
		}

		if (noteCount === 0) throw new Error("no data")

		// 评分：笔记(40) + 点赞(30) + 收藏(30) — 简化版
		const noteScore = Math.min(40, (noteCount / 3) * 8)
		const likeScore = Math.min(30, Math.log10(Math.max(1, totalLike)) * 7)
		const score = Math.round(noteScore + likeScore + 15)

		return {
			score: Math.min(100, score),
			source: "real",
			raw: { noteCount, totalLike },
		}
	} catch (e) {
		return failedScore("xiaohongshu", e.message)
	}
}

// ===== QQ群 =====
async function fetchQQqun(keyword) {
	try {
		await randDelay()
		// 用搜狗web搜"QQ群 关键词"，不用weixin子域名避免验证码
		const searchKeyword = `QQ群 ${keyword}`
		const url = `https://www.sogou.com/web?query=${encodeURIComponent(searchKeyword)}`
		const res = await fetch(url, {
			headers: { ...DEFAULT_HEADERS, "Accept": "text/html" },
			redirect: "follow",
		})
		if (!res.ok) throw new Error(`HTTP ${res.status}`)
		const html = await res.text()

		// 提取结果数
		let resultCount = 0
		const countMatch = html.match(/搜狗已为您找到约?\s*([\d,]+)\s*条/) || html.match(/找到约\s*([\d,]+)\s*条/)
		if (countMatch) {
			resultCount = Number.parseInt(countMatch[1].replace(/,/g, ""), 10)
		} else {
			// 备选：数QQ群号出现次数
			const qqMatches = html.match(/\d{5,10}/g) || []
			resultCount = qqMatches.length
		}

		// 评分：log10(结果数) * 15，封顶 100
		const score = Math.min(100, Math.round(Math.log10(Math.max(1, resultCount)) * 15))

		return {
			score,
			source: "real",
			raw: { resultCount },
		}
	} catch (e) {
		return failedScore("qq", e.message)
	}
}

// ===== 失败回退（score 为 null，不参与权重计算） =====
function failedScore(platform, error) {
	return {
		score: null,
		source: "failed",
		raw: { error: error || "API 抓取失败" },
	}
}

// ===== 主入口 =====
export async function fetchMediaHeat(school, major) {
	const keyword = `${school} ${major} 考研`

	const results = await Promise.allSettled([
		fetchBilibili(keyword),
		fetchZhihu(keyword),
		fetchBaidu(keyword),
		fetchDouyin(keyword),
		fetchTieba(keyword),
		fetchWechat(keyword),
		fetchXiaohongshu(keyword),
		fetchQQqun(keyword),
	])

	const platformsRaw = {
		bilibili: results[0].status === "fulfilled" ? results[0].value : failedScore("bilibili", "rejected"),
		zhihu: results[1].status === "fulfilled" ? results[1].value : failedScore("zhihu", "rejected"),
		baidu: results[2].status === "fulfilled" ? results[2].value : failedScore("baidu", "rejected"),
		douyin: results[3].status === "fulfilled" ? results[3].value : failedScore("douyin", "rejected"),
		tieba: results[4].status === "fulfilled" ? results[4].value : failedScore("tieba", "rejected"),
		wechat: results[5].status === "fulfilled" ? results[5].value : failedScore("wechat", "rejected"),
		xiaohongshu: results[6].status === "fulfilled" ? results[6].value : failedScore("xiaohongshu", "rejected"),
		qq: results[7].status === "fulfilled" ? results[7].value : failedScore("qq", "rejected"),
	}

	// 原始权重（参考原系统，微博已移除）
	const baseWeights = {
		bilibili: 0.24, zhihu: 0.03, tieba: 0.13, baidu: 0.16,
		douyin: 0.14, wechat: 0.05, xiaohongshu: 0.09, qq: 0.16,
	}

	// 过滤失败平台（score 为 null），重新归一化权重
	const successPlatforms = {}
	const failedPlatforms = []
	let totalWeight = 0
	for (const [k, v] of Object.entries(platformsRaw)) {
		if (v.score !== null) {
			successPlatforms[k] = v
			totalWeight += baseWeights[k]
		} else {
			failedPlatforms.push(k)
		}
	}

	// 动态权重：成功平台按比例重新分配
	const weights = {}
	for (const k of Object.keys(successPlatforms)) {
		weights[k] = totalWeight > 0 ? baseWeights[k] / totalWeight : 0
	}

	// 计算媒体热度
	let compositeScore = 0
	for (const [k, v] of Object.entries(successPlatforms)) {
		compositeScore += v.score * weights[k]
	}
	const mediaHeat = Math.round(Math.min(100, Math.max(0, compositeScore)))

	// 合并输出（失败平台保留，score 为 null）
	const platforms = { ...platformsRaw }
	for (const k of Object.keys(successPlatforms)) {
		platforms[k] = { ...successPlatforms[k], weight: Number(weights[k].toFixed(3)) }
	}

	return {
		mediaHeat,
		successCount: Object.keys(successPlatforms).length,
		failedCount: failedPlatforms.length,
		failedPlatforms,
		platforms,
		keyword,
	}
}

// CLI 测试
if (import.meta.url === `file://${process.argv[1]}`) {
	const school = process.argv[2] || "南京大学"
	const major = process.argv[3] || "生物学"
	console.log(`正在抓取 "${school} ${major} 考研" 的媒体热度...\n`)
	const start = Date.now()
	const result = await fetchMediaHeat(school, major)
	console.log(`耗时: ${Date.now() - start}ms`)
	console.log(`媒体热度: ${result.mediaHeat}/100 (成功: ${result.successCount}/8 平台，失败: ${result.failedPlatforms.join(", ") || "无"})`)
	console.log("\n各平台详情:")
	for (const [k, v] of Object.entries(result.platforms)) {
		if (v.score === null) {
			console.log(`  ❌ ${k.padEnd(12)} 抓取失败  (${v.source})`)
		} else {
			const icon = v.source === "real" ? "✅" : "⚠️"
			console.log(`  ${icon} ${k.padEnd(12)} ${String(v.score).padStart(3)} 分  (权重 ${Math.round((v.weight || 0) * 100)}%)`)
		}
	}
}
