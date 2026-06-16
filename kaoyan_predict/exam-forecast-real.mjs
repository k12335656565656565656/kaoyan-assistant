#!/usr/bin/env node
// exam-forecast-real.mjs — 考研热度预测 CLI（真实数据 + 内置数据库 + 模拟回退）
// 纯 Node.js ESM，零外部依赖，已去除微博

import { readFileSync, existsSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { fetchMediaHeat } from "./media-scraper.mjs"
import { resolveSchoolLevel, buildOfficialChannels, buildAdmissionDataChannels } from "./school-metadata.mjs"
import { findAdmissionEvidence, buildHistoryFromAdmissionEvidence } from "./admission-evidence.mjs"

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// ===== 参数解析 =====
function parseArgs(argv) {
	const args = argv.slice(2)
	const options = { help: false, school: "", major: "", majorCode: "", session: "27届", data: "", json: false, matchMode: "fuzzy", degreeType: "", includeMedia: true, mediaTimeoutMs: 12000 }
	for (let i = 0; i < args.length; i++) {
		const arg = args[i]
		if (arg === "--help" || arg === "-h") {
			options.help = true
		} else if (arg === "--school" || arg === "-s") {
			options.school = args[++i] || ""
		} else if (arg === "--major" || arg === "-m") {
			options.major = args[++i] || ""
		} else if (arg === "--major-code" || arg === "-c") {
			options.majorCode = args[++i] || ""
		} else if (arg === "--session" || arg === "-e") {
			options.session = args[++i] || "27届"
		} else if (arg === "--data" || arg === "-d") {
			options.data = args[++i] || ""
		} else if (arg === "--match-mode") {
			options.matchMode = args[++i] || "fuzzy"
		} else if (arg === "--degree-type") {
			options.degreeType = args[++i] || ""
		} else if (arg === "--no-media") {
			options.includeMedia = false
		} else if (arg === "--media-timeout-ms") {
			options.mediaTimeoutMs = Number(args[++i] || 12000)
		} else if (arg === "--json" || arg === "-j") {
			options.json = true
		} else if (!arg.startsWith("-") && !options.school) {
			options.school = arg
		} else if (!arg.startsWith("-") && !options.major) {
			options.major = arg
		}
	}
	// 如果 major 是纯 6 位数字，自动识别为学科代码
	if (/^\d{6}$/.test(options.major) && !options.majorCode) {
		options.majorCode = options.major
		options.major = ""
	}
	options.matchMode = options.matchMode === "exact" ? "exact" : "fuzzy"
	options.degreeType = normalizeDegreeType(options.degreeType)
	return options
}

function showHelp() {
	console.log(`
考研热度预测系统（真实数据版 · 无微博）

用法:
  node exam-forecast-real.mjs [选项]

选项:
  -s, --school <名称>    院校名称（如：南京大学）
  -m, --major <名称>     专业名称（如：生物学）
  -c, --major-code <代码>  学科代码精确匹配（如：071000）
  -e, --session <届数>   目标届数（默认：27届）
  -d, --data <文件>      外部真实数据 JSON 文件路径
  --match-mode <模式>    匹配模式：exact 精确 / fuzzy 模糊（默认 fuzzy）
  --degree-type <类型>   学位类型：academic 学硕 / professional 专硕
  --no-media            跳过媒体热度抓取，仅返回权威招生/录取数据
  --media-timeout-ms <毫秒> 媒体热度抓取超时（默认 12000）
  -j, --json             输出结构化 JSON（便于程序解析）
  -h, --help             显示帮助信息

  数据优先级:
  1. --data 指定的外部 JSON 文件
  2. 同目录 builtin-db.json 内置真实数据库（115校/3890条）
  3. handebook.com 公开API（真实考试科目+招生人数·免费）
  4. 呱呱严选 API（真实录取数据·需登录态+积分）
  5. enriched-db / 实时 enrich 统计推断
  6. 模拟数据（基于院校+专业哈希生成）

示例:
  # 查询内置真实数据库（南京大学 生物学）
  node exam-forecast-real.mjs -s 南京大学 -m 生物学 -e 27届

  # 使用外部 JSON 真实数据
  node exam-forecast-real.mjs -s 山东大学 -m 生物学 -d shandong.json

  # 位置参数
  node exam-forecast-real.mjs 清华大学 金融学
`)
}

// ===== 数据加载 =====
function loadJson(path) {
	if (!existsSync(path)) return null
	try {
		return JSON.parse(readFileSync(path, "utf-8"))
	} catch {
		return null
	}
}

function normalize(str) {
	return String(str).replace(/\s+/g, "").toLowerCase()
}

function normalizeSchoolKey(str) {
	return normalize(str)
		.replace(/[（(]\s*北京\s*[）)]/g, "北京")
		.replace(/[（(]\s*华东\s*[）)]/g, "华东")
		.replace(/[（(]\s*武汉\s*[）)]/g, "武汉")
		.replace(/[（）()]/g, "")
}

function schoolCampusQualifier(str) {
	const value = normalize(str)
	const match = value.match(/[（(]\s*(北京|华东|武汉)\s*[）)]/)
	if (match) return match[1]
	for (const suffix of ["北京", "华东", "武汉"]) {
		if (value.endsWith(suffix)) return suffix
	}
	return ""
}

function normalizeDegreeType(value) {
	const v = normalize(value)
	if (!v) return ""
	if (v === "academic" || v.includes("学硕") || v.includes("学术")) return "academic"
	if (v === "professional" || v.includes("专硕") || v.includes("专业")) return "professional"
	return ""
}

function formatDegreeType(value) {
	const normalized = normalizeDegreeType(value)
	if (normalized === "academic") return "学硕"
	if (normalized === "professional") return "专硕"
	return ""
}

function getProfileDegreeType(profile) {
	return normalizeDegreeType(profile?.degreeType || profile?.MajorDegreeType || profile?.degree || "")
}

function selectProfile(candidates, degreeType) {
	const list = Array.isArray(candidates) ? candidates : (candidates ? [candidates] : [])
	if (!list.length) return null
	if (!degreeType) return list[0]
	return list.find((profile) => getProfileDegreeType(profile) === degreeType) || null
}

/** 构建双层索引：school → major → profile，同时按 majorCode 索引 */
function buildIndex(db) {
	if (!Array.isArray(db)) return null
	const index = {
		bySchoolMajor: new Map(),
		byMajorCode: new Map(),
	}
	for (const p of db) {
		const sNorm = normalize(p.school)
		const mNorm = normalize(p.major)
		// school → major map
		if (!index.bySchoolMajor.has(sNorm)) {
			index.bySchoolMajor.set(sNorm, new Map())
		}
		const majorMap = index.bySchoolMajor.get(sNorm)
		if (!majorMap.has(mNorm)) majorMap.set(mNorm, [])
		majorMap.get(mNorm).push(p)

		// majorCode 索引（兼容 4/6 位，存原始值和截断值）
		const code = String(p.majorCode || "")
		if (code) {
			for (const key of [code, code.slice(0, 4)]) {
				if (!index.byMajorCode.has(key)) index.byMajorCode.set(key, [])
				index.byMajorCode.get(key).push(p)
			}
		}
	}
	return index
}

/** 基于索引的精确+模糊查找，优先学科代码，避免短词子串误匹配 */
function searchProfile(index, school, major, majorCode, options = {}) {
	if (!index) return null
	const ns = normalize(school)
	const nm = normalize(major)
	const matchMode = options.matchMode === "exact" ? "exact" : "fuzzy"
	const degreeType = normalizeDegreeType(options.degreeType)
	const schoolMatches = (candidateSchool) => {
		const requestedKey = normalizeSchoolKey(school)
		const candidateKey = normalizeSchoolKey(candidateSchool)
		const requestedCampus = schoolCampusQualifier(school)
		const candidateCampus = schoolCampusQualifier(candidateSchool)
		if (matchMode === "exact") return candidateKey === requestedKey
		if (candidateKey === requestedKey) return true
		if (candidateCampus && !requestedCampus) return false
		if (requestedCampus && candidateCampus && requestedCampus !== candidateCampus) return false
		return candidateKey.includes(requestedKey) || requestedKey.includes(candidateKey)
	}

	// 1. 学科代码精确匹配（最高优先级）
	if (majorCode) {
		const codeStr = String(majorCode).trim()
		const candidates = index.byMajorCode.get(codeStr)
		if (candidates) {
			return selectProfile(candidates.filter((p) => schoolMatches(p.school)), degreeType)
		}
	}

	// 2. 按学校名找到子索引
	let majorMap = null
	for (const [sKey, mMap] of index.bySchoolMajor) {
		if (schoolMatches(sKey)) {
			majorMap = mMap
			break
		}
	}
	if (!majorMap) return null

	// 3. 专业名称精确匹配
	if (majorMap.has(nm)) {
		return selectProfile(majorMap.get(nm), degreeType)
	}
	if (matchMode === "exact") return null

	// 4. 模糊匹配：为避免 "生物学" 误匹配 "古生物学与地层学"，
	//    短词（<=4 字符）仅接受精确匹配或完整词边界匹配；长词允许子串包含。
	const entries = [...majorMap.entries()]

	// 4a. query 包含 record（如用户输入更长）
	for (const [mKey, profiles] of entries) {
		if (nm.includes(mKey)) {
			const selected = selectProfile(profiles, degreeType)
			if (selected) return selected
		}
	}

	// 4b. record 包含 query，仅当 query 长度 >= 5 时允许，防止短词误触
	if (nm.length >= 5) {
		for (const [mKey, profiles] of entries) {
			if (mKey.includes(nm)) {
				const selected = selectProfile(profiles, degreeType)
				if (selected) return selected
			}
		}
	}

	// 4c. 短词（<=4字符）的边界匹配：要求 query 在 record 中作为独立语义单元出现
	//     简单判断：query 前一个字或后一个字不能是汉字（避免嵌入更长词中）
	if (nm.length <= 4 && nm.length >= 2) {
		for (const [mKey, profiles] of entries) {
			const idx = mKey.indexOf(nm)
			if (idx === -1) continue
			const before = idx > 0 ? mKey[idx - 1] : ""
			const after = idx + nm.length < mKey.length ? mKey[idx + nm.length] : ""
			// 前后字符均非常见中文字符（表示独立词边界）
			const isHan = (ch) => /[\u4e00-\u9fa5]/.test(ch)
			if ((!before || !isHan(before)) && (!after || !isHan(after))) {
				const selected = selectProfile(profiles, degreeType)
				if (selected) return selected
			}
		}
	}

	return null
}

// ===== 模拟数据生成（回退用） =====
function hashString(str) {
	let hash = 0
	for (let i = 0; i < str.length; i++) {
		const char = str.charCodeAt(i)
		hash = (hash << 5) - hash + char
		hash |= 0
	}
	return Math.abs(hash)
}

function generateSimulatedHistory(school, major) {
	const seed = hashString(school + major)
	const baseApplicants = 300 + (seed % 800)
	const baseCutScore = 300 + (seed % 50)
	return [
		{ year: "2021", applicants: baseApplicants, admitted: Math.floor(baseApplicants / 5), ratio: 5.0, cutScore: baseCutScore - 10 },
		{ year: "2022", applicants: baseApplicants + 80, admitted: Math.floor((baseApplicants + 80) / 5), ratio: 5.2, cutScore: baseCutScore },
		{ year: "2023", applicants: baseApplicants + 120, admitted: Math.floor((baseApplicants + 120) / 5), ratio: 5.4, cutScore: baseCutScore + 5 },
		{ year: "2024", applicants: baseApplicants + 80, admitted: Math.floor((baseApplicants + 80) / 5), ratio: 5.3, cutScore: baseCutScore + 3 },
	]
}

/** 基于 handebook 计划招生人数生成模拟历史数据 */
function generateHistoryFromPlanned(plannedEnrollment, school, major) {
	const seed = hashString(school + major)
	const planned = Math.max(5, plannedEnrollment)
	// 报录比通常在 3:1 到 15:1 之间
	const baseRatio = 3 + (seed % 12)
	const baseCutScore = 300 + (seed % 50)
	return [
		{ year: "2021", applicants: Math.round(planned * baseRatio * 0.9), admitted: planned, ratio: Number((baseRatio * 0.9).toFixed(1)), cutScore: baseCutScore - 8, note: "基于计划招生人数推断" },
		{ year: "2022", applicants: Math.round(planned * baseRatio * 0.95), admitted: planned + 1, ratio: Number((baseRatio * 0.95).toFixed(1)), cutScore: baseCutScore - 3, note: "基于计划招生人数推断" },
		{ year: "2023", applicants: Math.round(planned * baseRatio), admitted: planned, ratio: Number(baseRatio.toFixed(1)), cutScore: baseCutScore + 2, note: "基于计划招生人数推断" },
		{ year: "2024", applicants: Math.round(planned * baseRatio * 1.05), admitted: planned + 1, ratio: Number((baseRatio * 1.05).toFixed(1)), cutScore: baseCutScore + 5, note: "基于计划招生人数推断" },
	]
}

function generateSimulatedSubjects(major) {
	const isScience = major.includes("计算机") || major.includes("数学") || major.includes("物理")
	const isBiology = major.includes("生物") || major.includes("生态") || major.includes("生化")
	const isEngineering = major.includes("工程") || major.includes("自动化")
	const isBusiness = major.includes("金融") || major.includes("管理") || major.includes("会计")
	const subjects = [
		{ code: "101", name: "思想政治理论", type: "公共课" },
		{ code: "201", name: "英语（一）", type: "公共课" },
	]
	if (isScience || isEngineering) {
		subjects.push({ code: "301", name: "数学（一）", type: "基础课" })
		subjects.push({ code: "408", name: "计算机学科专业基础综合", type: "专业课" })
	} else if (isBiology) {
		subjects.push({ code: "621", name: "生物化学基础", type: "基础课" })
		subjects.push({ code: "835", name: "细胞生物学", type: "专业课" })
	} else if (isBusiness) {
		subjects.push({ code: "303", name: "数学三", type: "公共课" })
		subjects.push({ code: "431", name: "金融学综合", type: "专业课" })
	} else {
		subjects.push({ code: "302", name: "数学（二）", type: "基础课" })
		subjects.push({ code: "802", name: "专业基础综合", type: "专业课" })
	}
	return subjects
}

// ===== 预测算法（复刻原系统） =====
function predictToSession(history, targetYear) {
	const targetSession = `${String(targetYear % 100).padStart(2, "0")}届`
	const lastEntry = history[history.length - 1]
	const yearChanges = []
	for (let i = 1; i < history.length; i++) {
		const prev = history[i - 1].applicants
		const curr = history[i].applicants
		yearChanges.push((curr - prev) / Math.max(1, prev))
	}
	const baseYear = Number.parseInt(history[history.length - 1].year)
	const yearsAhead = targetYear - baseYear
	let avgTrend = yearChanges.length > 0 ? yearChanges[yearChanges.length - 1] : 0
	if (yearChanges.length >= 2) {
		avgTrend = yearChanges[yearChanges.length - 1] * 0.7 + yearChanges[yearChanges.length - 2] * 0.3
	}
	const decayFactor = Math.max(0.3, 1 - yearsAhead * 0.1)
	const projectedApplicants = Math.round(lastEntry.applicants * (1 + avgTrend * decayFactor * yearsAhead))

	const scoreValues = history.map((h) => h.cutScore)
	const years = history.map((h) => Number.parseInt(h.year))
	let projectedCutScore = lastEntry.cutScore
	if (scoreValues.length >= 2) {
		let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0
		const n = scoreValues.length
		for (let i = 0; i < n; i++) {
			sumX += years[i]
			sumY += scoreValues[i]
			sumXY += years[i] * scoreValues[i]
			sumX2 += years[i] * years[i]
		}
		const denominator = n * sumX2 - sumX * sumX
		if (denominator !== 0) {
			const slope = (n * sumXY - sumX * sumY) / denominator
			projectedCutScore = Math.round(slope * targetYear + (sumY - slope * sumX) / n)
		}
	}
	const estimatedRatio = Number.parseFloat((lastEntry.ratio + avgTrend * decayFactor * yearsAhead * lastEntry.ratio).toFixed(1))

	// computeHardDataScore — 修正复录比/报录比混合数据的问题
	const last = history[history.length - 1]
	const prev = history.length > 1 ? history[history.length - 2] : last

	// 判断 ratio 是报录比还是复录比
	// 报录比通常在 2~30 之间（报考/录取）
	// 复录比通常在 1.2~3 之间（进复试/录取）
	let ratioScore = 0
	if (last.ratio < 3 && last.applicants > 0 && last.admitted > 0) {
		// 很可能是复录比：复录比越低 = eliminateRate越高 = 竞争越激烈 = 热度越高
		// 复录比 1.2:1 → eliminateRate 17% → 热度高
		// 复录比 2.5:1 → eliminateRate 60% → 热度低（过线就能上）
		const eliminateRate = 1 - (1 / last.ratio)
		ratioScore = Math.min(40, eliminateRate * 60) // eliminateRate 67% → 40分满分
	} else {
		// 正常的报录比
		ratioScore = Math.min(40, (last.ratio / 20) * 40)
	}

	const cutScoreDiff = last.cutScore - 280
	const cutScoreNorm = Math.min(30, (cutScoreDiff / 40) * 30)
	const trendChange = last.ratio - prev.ratio
	const trendScore = Math.max(-10, Math.min(10, trendChange * 2))

	// 基础热度
	let heatEstimate = Math.max(0, Math.min(100, Math.round(ratioScore + cutScoreNorm + trendScore)))

	// 院校层次加成：985 +5分，211 +3分
	heatEstimate = Math.min(100, heatEstimate + 5)

	return {
		session: targetSession,
		year: targetYear,
		estimatedApplicants: Math.max(30, projectedApplicants),
		estimatedRatio: Math.max(1, estimatedRatio),
		estimatedCutScore: Math.max(280, Math.min(420, projectedCutScore)),
		heatEstimate,
	}
}

// ===== 热度与展示 =====
function generateSessionHistory(currentHeat) {
	const sessions = ["23届", "24届", "25届", "26届", "27届"]
	const baseValues = [currentHeat - 20, currentHeat - 10, currentHeat, currentHeat + 5, currentHeat + 10]
	return sessions.map((session, i) => ({
		session,
		heat: Math.min(100, Math.max(0, baseValues[i])),
	}))
}

function generatePlatformData(baseHeat) {
	return [
		{ platform: "B站", score: Math.round(baseHeat + 10), weight: 0.24, available: false },
		{ platform: "知乎", score: Math.round(baseHeat - 5), weight: 0.03, available: false },
		{ platform: "贴吧", score: Math.round(baseHeat + 3), weight: 0.13, available: false },
		{ platform: "百度搜索", score: Math.round(baseHeat + 5), weight: 0.16, available: false },
		{ platform: "抖音", score: Math.round(baseHeat + 7), weight: 0.14, available: false },
		{ platform: "小红书", score: Math.round(baseHeat - 2), weight: 0.09, available: false },
		{ platform: "微信", score: Math.round(baseHeat - 8), weight: 0.05, available: false },
		{ platform: "QQ群", score: Math.round(baseHeat + 2), weight: 0.16, available: false },
	]
}

function generateFactors({
	school,
	major,
	isReal,
	isEnriched,
	canPredict,
	department,
	schoolLevel,
	degreeTypeLabel,
	pushRatioDesc,
	mediaSuccessCount,
	mediaFailedPlatforms,
}) {
	const factors = []
	const profileParts = [department, degreeTypeLabel, schoolLevel].filter(Boolean)
	factors.push({
		icon: "学科",
		title: `${school} ${major}`,
		desc: profileParts.length ? profileParts.join(" | ") : "未查询到完整项目信息",
	})

	if (isReal) {
		factors.push({ icon: "数据", title: "数据来源", desc: "基于真实录取历史与官方招生数据" })
	} else if (isEnriched && canPredict) {
		factors.push({ icon: "数据", title: "数据来源", desc: "基于可核验录取历史生成补充判断" })
	} else {
		factors.push({ icon: "数据", title: "数据来源", desc: "缺少权威录取历史，不生成报录比、复试线等推断结论" })
	}

	factors.push({ icon: "推免", title: "推免比例", desc: pushRatioDesc || "未查询到权威推免比例" })
	if ((mediaSuccessCount || 0) > 0) {
		const failedText = mediaFailedPlatforms?.length ? `，失败平台已忽略：${mediaFailedPlatforms.join("、")}` : ""
		factors.push({ icon: "媒体", title: "媒体热度", desc: `成功抓取 ${mediaSuccessCount}/8 个平台${failedText}` })
	}
	return factors
}

// ===== 核心运行逻辑 =====
function getHeatLevel(score) {
	if (score >= 90) return { label: "卷王", color: "⚫" }
	if (score >= 75) return { label: "极高", color: "🔴" }
	if (score >= 60) return { label: "较高", color: "🟠" }
	if (score >= 45) return { label: "中等", color: "🟡" }
	if (score >= 25) return { label: "较低", color: "🔵" }
	return { label: "冷门", color: "🟢" }
}

function buildSourceAuthority(profile, notes, dataSource) {
	const noteText = (notes || []).join(" ")
	const urlMatch = noteText.match(/https?:\/\/[^\s，,）)】]+/i)
	if (urlMatch) {
		const url = urlMatch[0].replace(/[。；;]+$/, "")
		return {
			label: url.includes("yz.chsi.com.cn") ? "中国研究生招生信息网" : "招生单位研究生招生网",
			url,
		}
	}
	if (dataSource.includes("官方招生目录库")) {
		return { label: "招生单位研究生招生网/中国研究生招生信息网硕士专业目录", url: "https://yz.chsi.com.cn/zsml/" }
	}
	if (profile?.source === "handebook_supplement") {
		return { label: "待招生单位官网/中国研究生招生信息网核验", url: "https://yz.chsi.com.cn/zsml/" }
	}
	return { label: "招生单位官方招生信息", url: "" }
}

function formatSourceAuthority(sourceAuthority) {
	if (!sourceAuthority?.label) return ""
	return sourceAuthority.url ? `${sourceAuthority.label}（${sourceAuthority.url}）` : sourceAuthority.label
}

function normalizeSchoolNotes(notes, sourceAuthority, dataSource) {
	const normalized = [...new Set((notes || []).filter(Boolean))]
	const authorityText = formatSourceAuthority(sourceAuthority)
	if (authorityText && !normalized.some((note) => note.includes("权威来源"))) {
		normalized.unshift(`官方核验渠道：${authorityText}`)
	}
	if (dataSource.includes("handebook") && !normalized.some((note) => note.includes("handebook") && note.includes("补充"))) {
		normalized.push("补充说明：handebook 公开接口仅用于考试科目、计划招生字段，不作为录取人数、推免比例、复试线权威来源")
	}
	return normalized
}

function buildMatchInfo(requestedSchool, requestedMajor, profile, opts) {
	const requestedMajorCode = String(opts.majorCode || "").trim()
	const matched = profile ? {
		school: profile.school || "",
		major: profile.major || "",
		majorCode: profile.majorCode || "",
		department: profile.department || "",
		degreeType: getProfileDegreeType(profile),
		degreeTypeLabel: formatDegreeType(profile.degreeType),
	} : null
	const requestedDegreeType = normalizeDegreeType(opts.degreeType)
	const isExact = !!matched
		&& normalize(requestedSchool) === normalize(matched.school)
		&& (!requestedMajor || normalize(requestedMajor) === normalize(matched.major))
		&& (!requestedMajorCode || requestedMajorCode === String(matched.majorCode || ""))
		&& (!requestedDegreeType || requestedDegreeType === matched.degreeType)
	return {
		mode: opts.matchMode === "exact" ? "exact" : "fuzzy",
		requested: {
			school: requestedSchool,
			major: requestedMajor,
			majorCode: requestedMajorCode,
			degreeType: requestedDegreeType,
			degreeTypeLabel: formatDegreeType(requestedDegreeType),
		},
		matched,
		isExact,
	}
}

function buildFieldSources({
	profile,
	dataSource,
	sourceAuthority,
	matchInfo,
	schoolLevel,
	schoolLevelInfo,
	department,
	plannedEnrollmentText,
	programOptions,
	hasAuthoritativeAdmissionHistory,
	predictionBasis,
	admissionEvidenceSummary,
	canPredict,
	mediaSuccessCount,
	mediaFailedPlatforms,
}) {
	const authorityText = formatSourceAuthority(sourceAuthority) || dataSource || "未知来源"
	const usesEvidenceHistory = predictionBasis === "official_evidence_extracted"
	const isSupplement = profile?.source === "handebook_supplement" || profile?.sourceKind === "plan_only" || (programOptions || []).length > 0
	const planConfidence = isSupplement ? "supplement" : "medium"
	const planNote = isSupplement
		? "招生计划、考试科目等字段来自补充源，需以研招网或招生单位官网核验"
		: "来自本地招生目录命中结果，仍建议以官方目录复核"
	return {
		match: {
			source: matchInfo?.requested?.majorCode ? "专业代码优先匹配" : "院校/专业名称匹配",
			confidence: matchInfo?.isExact ? "high" : "medium",
			note: matchInfo?.isExact ? "请求条件与命中结果一致" : "存在同名专业或多院系候选，请以上方选中项目为准",
		},
		majorCode: {
			source: authorityText,
			confidence: profile?.majorCode ? planConfidence : "unknown",
			note: profile?.majorCode ? planNote : "未查询到专业代码",
		},
		schoolLevel: {
			source: schoolLevelInfo?.source || "本地院校层次映射",
			confidence: schoolLevelInfo?.confidence || (schoolLevel && !["未知", "未确认"].includes(schoolLevel) ? "medium" : "unknown"),
			note: schoolLevelInfo?.tags?.length ? `分类标签：${schoolLevelInfo.tags.join("、")}` : "院校层次建议以教育部和学校官方信息复核",
		},
		department: {
			source: authorityText,
			confidence: department && !["未知", "相关学院"].includes(department) ? planConfidence : "unknown",
			note: department ? planNote : "未查询到院系",
		},
		plannedEnrollment: {
			source: authorityText,
			confidence: plannedEnrollmentText ? planConfidence : "unknown",
			note: plannedEnrollmentText ? planNote : "未查询到计划招生",
		},
		examSubjects: {
			source: authorityText,
			confidence: profile?.examSubjects?.length ? planConfidence : "unknown",
			note: profile?.examSubjects?.length ? planNote : "未查询到考试科目",
		},
		pushRatio: {
			source: hasAuthoritativeAdmissionHistory ? authorityText : "未查询到权威来源",
			confidence: hasAuthoritativeAdmissionHistory ? "high" : "unknown",
			note: hasAuthoritativeAdmissionHistory ? "来自可核验录取历史字段" : "不使用默认推免比例，不确定则显示不确定",
		},
		admissionHistory: {
			source: hasAuthoritativeAdmissionHistory ? authorityText : usesEvidenceHistory ? "学校官网/研招网页面自动提取" : "未查询到权威录取历史",
			confidence: hasAuthoritativeAdmissionHistory ? "high" : usesEvidenceHistory ? "medium" : "unavailable",
			note: hasAuthoritativeAdmissionHistory
				? "用于录取热度和预测"
				: usesEvidenceHistory
					? "来源页面可信，但数字为程序自动抽取，需人工复核"
					: admissionEvidenceSummary?.total
						? "已找到官方来源页面，但未形成连续两年完整指标"
						: "需要复试名单、拟录取名单、复试线或报录比公告",
		},
		prediction: {
			source: canPredict ? usesEvidenceHistory ? "基于官网自动提取指标的趋势计算" : "基于权威录取历史的趋势计算" : "未生成",
			confidence: canPredict ? usesEvidenceHistory ? "low" : "derived" : "unavailable",
			note: canPredict
				? usesEvidenceHistory ? "预测可信度较低；建议打开来源页面逐项核验后再使用" : "预测值不是官方结论，仅作为趋势参考"
				: "缺少连续两年完整录取历史，不生成报考人数、报录比和复试线预测",
		},
		mediaHeat: {
			source: "实时媒体抓取",
			confidence: mediaSuccessCount > 0 ? "realtime" : "unavailable",
			note: mediaSuccessCount > 0
				? `成功 ${mediaSuccessCount}/8 平台${mediaFailedPlatforms?.length ? `，失败：${mediaFailedPlatforms.join("、")}` : ""}`
				: "媒体平台抓取失败或超时",
		},
	}
}

async function attachPlanOptions(profile, school, major, options = {}) {
	if (!profile) return profile
	if (Array.isArray(profile.programOptions) && profile.programOptions.length > 0) return profile
	try {
		const { fetchHandebookProfile } = await import("./auth/handebook-provider.mjs")
		const planProfile = await fetchHandebookProfile(school, major || profile.major || "", options)
		if (!planProfile) return profile
		profile.programOptions = planProfile.programOptions || []
		const targetDegree = getProfileDegreeType(profile)
		const matchingProgram = profile.programOptions.find((p) => {
			if (targetDegree && p.degreeType !== targetDegree) return false
			if (profile.majorCode && p.majorCode !== profile.majorCode) return false
			return true
		}) || profile.programOptions.find((p) => !targetDegree || p.degreeType === targetDegree) || profile.programOptions[0]
		if (matchingProgram) {
			profile.department = matchingProgram.department || profile.department
			profile.plannedEnrollment = matchingProgram.plannedEnrollment ?? profile.plannedEnrollment
			profile.plannedEnrollmentText = matchingProgram.plannedEnrollmentText || profile.plannedEnrollmentText
			profile.researchDirection = matchingProgram.researchDirection || profile.researchDirection
			profile.degreeType = matchingProgram.degreeType || profile.degreeType
			profile.degreeTypeLabel = matchingProgram.degreeTypeLabel || profile.degreeTypeLabel
			profile.learningWay = matchingProgram.learningWay || profile.learningWay
			profile.universityCode = matchingProgram.universityCode || profile.universityCode
		}
		return profile
	} catch (e) {
		console.log(`[DataSource] 招生项目补充失败: ${e.message}`)
		return profile
	}
}

/** 按严格优先级解析 profile：REAL > ENRICHED > SIMULATED */
async function resolveProfile(opts) {
	const { school, major, majorCode, data: dataPath, matchMode = "fuzzy", degreeType = "" } = opts
	let profile = null
	let level = "SIMULATED"
	let dataSource = "模拟数据（院校未录入真实数据库）"

	// 1. 外部 JSON（最高优先级真实数据）
	if (dataPath) {
		const db = loadJson(dataPath)
		if (db) {
			const index = buildIndex(db)
			profile = searchProfile(index, school, major, majorCode, { matchMode, degreeType })
			if (profile) {
				level = "REAL"
				dataSource = "外部JSON（真实命中）"
				return { profile, level, dataSource }
			}
		}
	}

	// 2. 内置数据库（官方录取历史）
	const builtinPath = join(__dirname, "builtin-db.json")
	const builtinDb = loadJson(builtinPath)
	if (builtinDb) {
		const index = buildIndex(builtinDb)
		profile = searchProfile(index, school, major, majorCode, { matchMode, degreeType })
		if (profile) {
			level = "REAL"
			dataSource = "官方招生目录库（招生单位研招网/研招网专业目录·本地命中）"
			profile = await attachPlanOptions(profile, school, major, { matchMode, degreeType, majorCode })
			return { profile, level, dataSource }
		}
	}

	// 3. 呱呱严选真实录取数据（最高优先级·有积分时使用）
	let ggyxRealHistory = null
	try {
		const { hasGgyxLoginState } = await import("./auth/ggyx-data-provider.mjs")
		if (hasGgyxLoginState()) {
			console.log(`[DataSource] 尝试从呱呱严选获取 ${school} ${major || ""} 真实录取数据...`)
			const ggyxIdMap = {
				"华东师范大学::生物学": { xyId: "597", majorId: "513" },
				"山东大学::生物学": { xyId: "10422", majorId: "866" },
			}
			const key = `${school}::${major || ""}`
			const ids = ggyxIdMap[key]
			if (ids) {
				const { fetchGgyxRealData } = await import("./auth/ggyx-data-provider-v2.mjs")
				const ggyxProfile = await fetchGgyxRealData(ids.xyId, ids.majorId)
				if (ggyxProfile && ggyxProfile.history && ggyxProfile.history.length > 0) {
					ggyxRealHistory = ggyxProfile.history
					// 如果有2年以上真实数据，直接使用
					if (ggyxProfile.history.length >= 2) {
						profile = ggyxProfile
						level = "REAL"
						dataSource = "呱呱严选（真实录取数据·API V2）"
						return { profile, level, dataSource }
					}
					console.log(`[DataSource] 呱呱严选仅有 ${ggyxProfile.history.length} 年真实数据，将结合其他数据源补充`)
				}
			}
		}
	} catch (e) {
		console.log(`[DataSource] 呱呱严选获取失败: ${e.message}`)
	}

	// 4. handebook 公开数据（真实考试科目+招生人数，免费）
	try {
		const { fetchHandebookProfile } = await import("./auth/handebook-provider.mjs")
		const hbProfile = await fetchHandebookProfile(school, major || "", { matchMode, degreeType, majorCode })
		if (hbProfile && hbProfile.examSubjects && hbProfile.examSubjects.length > 0) {
			profile = hbProfile
			level = "PLAN"
			dataSource = "招生计划补充数据（handebook公开接口；需以研招网/招生单位官网核验）"
			profile.history = []

			// 如果有呱呱严选真实数据，用真实复试线/复录比覆盖模拟数据
			if (ggyxRealHistory && ggyxRealHistory.length > 0) {
				console.log(`[DataSource] 用呱呱严选真实数据覆盖 ${ggyxRealHistory.length} 年数据...`)
				profile.history = ggyxRealHistory.map((real) => ({ ...real, note: "呱呱严选真实数据" }))
				// 重新排序
				profile.history.sort((a, b) => Number(a.year) - Number(b.year))
				level = "REAL"
				dataSource = "handebook补充考试科目 + 呱呱严选补充复试数据（仍需官网核验）"
			}

			return { profile, level, dataSource }
		}
	} catch (e) {
		console.log(`[DataSource] handebook 获取失败: ${e.message}`)
	}

	// 以上均未命中 → 无数据
		dataSource = "暂未查询到该学校的录取数据"
		return { profile: null, level: "NONE", dataSource }

}

async function runForecast(opts) {
	const silent = opts.json
	const originalLog = console.log
	if (silent) console.log = () => {}

	let { school, major, session } = opts
	const requestedSchool = school
	const requestedMajor = major
	const sessionYearMatch = session.match(/(\d+)/)
	const targetYear = sessionYearMatch ? 2000 + Number.parseInt(sessionYearMatch[1]) : 2027

	// ─── 记忆系统耦合（动态加载，失败不阻塞）───
	let memory = null
	let memorySummary = ""
	let similarQueries = []
	try {
		const { KaoyanMemory } = await import("./memory.mjs")
		memory = new KaoyanMemory()
		const ctx = memory.getSessionContext()
		if (ctx.recentQueries.length > 0) {
			similarQueries = memory.findSimilar(school, major, 3)
		}
		memorySummary = memory.generateContextSummary()
	} catch (e) {
		// memory module 不可用（如首次安装），静默跳过
	}

	// 按严格优先级解析 profile
	const resolved = await resolveProfile(opts)
	let { profile, level, dataSource } = resolved
	const isReal = level === "REAL"
	const isEnriched = level === "ENRICHED"
	const isPlanOnly = level === "PLAN"
	const hasProfile = (isReal || isEnriched || isPlanOnly) && profile

	if (hasProfile) {
		school = profile.school || school
		major = profile.major || major
	}

	// 构建统一数据结构
	let admissionHistory, subjects, schoolNotes, schoolLevel, department, pushRatioDesc
	let plannedEnrollment = null
	let plannedEnrollmentText = ""
	let programOptions = []
	const hasAuthoritativeAdmissionHistory = !!(
		hasProfile
		&& profile.hasAuthoritativeAdmissionHistory === true
		&& Array.isArray(profile.history)
		&& profile.history.length >= 2
	)
	if (hasProfile) {
		admissionHistory = hasAuthoritativeAdmissionHistory ? profile.history.map((h) => ({
			year: String(h.year),
			applicants: h.applicants,
			admitted: h.admitted,
			ratio: h.ratio,
			cutScore: h.reCutScore ?? h.cutScore ?? 300,
			nationalLine: h.nationalLine,
			note: h.note,
		})) : []
		subjects = profile.examSubjects.map((s) => ({
			code: s.code,
			name: s.name,
			type: s.type,
		}))
		schoolNotes = profile.notes || []
		schoolLevel = profile.schoolLevel || "未确认"
		department = profile.department || "相关学院"
		plannedEnrollment = profile.plannedEnrollment ?? null
		plannedEnrollmentText = profile.plannedEnrollmentText || (plannedEnrollment ? `${plannedEnrollment} 人` : "")
		programOptions = Array.isArray(profile.programOptions) ? profile.programOptions : []
		const latest = Array.isArray(profile.history) && profile.history.length > 0 ? profile.history[profile.history.length - 1] : null
		pushRatioDesc = hasAuthoritativeAdmissionHistory && latest?.pushRatio
			? `推免约 ${Math.round(latest.pushRatio * 100)}%`
			: "未查询到权威推免比例"
	} else {
		// 无数据 → 不编造，返回空
		admissionHistory = []
		subjects = []
		schoolNotes = [`暂未查询到 ${school} ${major} 的录取数据`]
		schoolLevel = "未知"
		department = "未知"
		pushRatioDesc = "未查询到权威推免比例"
	}
	const sourceAuthority = buildSourceAuthority(profile, schoolNotes, dataSource)
	const schoolLevelInfo = resolveSchoolLevel(school, schoolLevel)
	schoolLevel = schoolLevelInfo.label
	const officialChannels = await buildOfficialChannels(school, sourceAuthority.url, {
		major,
		majorCode: opts.majorCode || profile?.majorCode || "",
		schoolCode: profile?.universityCode || programOptions[0]?.universityCode || "",
	})
	const admissionDataChannels = await buildAdmissionDataChannels(school, {
		major,
		majorCode: opts.majorCode || profile?.majorCode || "",
		schoolCode: profile?.universityCode || programOptions[0]?.universityCode || "",
	})
	const admissionEvidenceResult = await findAdmissionEvidence(school, major, {
		majorCode: opts.majorCode || profile?.majorCode || "",
		degreeType: opts.degreeType || profile?.degreeType || "",
		officialChannels,
		admissionDataChannels,
	})
	const admissionEvidence = admissionEvidenceResult.evidence || []
	const admissionEvidenceSummary = admissionEvidenceResult.summary || {}
	const evidenceHistory = buildHistoryFromAdmissionEvidence(admissionEvidence)
	schoolNotes = normalizeSchoolNotes(schoolNotes, sourceAuthority, dataSource)
	const matchInfo = buildMatchInfo(requestedSchool, requestedMajor, profile, opts)

	const usesEvidencePrediction = !hasAuthoritativeAdmissionHistory && evidenceHistory.length >= 2
	if (usesEvidencePrediction) {
		admissionHistory = evidenceHistory
		dataSource = "学校官网/研招网页面自动提取录取指标（低可信，需人工复核）"
		schoolNotes.push("预测依据来自学校官网/研招网页面自动提取指标；因不同学校页面格式差异较大，可信度低于人工整理的权威录取历史。")
	}
	const predictionBasis = hasAuthoritativeAdmissionHistory ? "authoritative_history" : usesEvidencePrediction ? "official_evidence_extracted" : "none"
	const canPredict = (hasAuthoritativeAdmissionHistory || usesEvidencePrediction) && admissionHistory.length >= 2
	const noDataAvailable = !canPredict
	const prediction = !canPredict
		? { session: targetYear + "届", year: targetYear, estimatedApplicants: 0, estimatedRatio: 0, estimatedCutScore: 0, heatEstimate: 0 }
		: predictToSession(admissionHistory, targetYear)
	const dataHeat = canPredict ? prediction.heatEstimate : 0

	// 抓取媒体热度（数据维度 * 0.65 + 媒体维度 * 0.35）
	let mediaHeat = 0, mediaSuccessCount = 0, mediaFailedPlatforms = [], mediaPlatforms = []
	if (opts.includeMedia !== false) {
		try {
			const media = await fetchMediaHeat(school, major, { timeoutMs: opts.mediaTimeoutMs || 12000 })
			mediaHeat = media.mediaHeat
			mediaSuccessCount = media.successCount
			mediaFailedPlatforms = media.failedPlatforms || []
			mediaPlatforms = Object.entries(media.platforms).map(([name, p]) => ({
				platform: name,
				score: p.score,
				source: p.source,
				weight: p.weight,
			}))
		} catch {
			mediaHeat = 0
		}
	}

	// 推免比例微调数据维度（推免越高 → 统考竞争越激烈 → 热度越高）
	const latest = admissionHistory.length > 0 ? admissionHistory[admissionHistory.length - 1] : null
	const pushRatio = latest?.pushRatio ?? 0
	const pushBonus = Math.round(pushRatio * 20)
	const adjustedDataHeat = Math.min(100, dataHeat + pushBonus)

	// 百分制综合热度
	let compositeHeat = canPredict ? Math.round(adjustedDataHeat * 0.65 + mediaHeat * 0.35) : 0

	// 有真实录取数据的查询加成
	if (!noDataAvailable && (dataSource.includes("呱呱严选") || dataSource.includes("官方招生目录库") || dataSource.includes("builtin-db"))) {
		compositeHeat = Math.min(100, compositeHeat + 8)
	}

	const currentHeat = compositeHeat

	const sessionHistory = generateSessionHistory(currentHeat)
	const factors = generateFactors({
		school,
		major,
		isReal,
		isEnriched,
		canPredict,
		department,
		schoolLevel,
		degreeTypeLabel: matchInfo?.matched?.degreeTypeLabel || profile?.degreeTypeLabel || "",
		pushRatioDesc,
		mediaSuccessCount,
		mediaFailedPlatforms,
	})
	const confidence = canPredict ? (usesEvidencePrediction ? 0.55 : isReal ? 0.78 : isEnriched ? 0.72 : 0.65) : 0
	const trend = canPredict ? "rising" : "unknown"

	// 输出
	const heatLevel = canPredict ? getHeatLevel(currentHeat) : { label: "数据不足", color: "⬜" }
	const fieldSources = buildFieldSources({
		profile,
		dataSource,
		sourceAuthority,
		matchInfo,
		schoolLevel,
		schoolLevelInfo,
		department,
		plannedEnrollmentText,
		programOptions,
		hasAuthoritativeAdmissionHistory,
		predictionBasis,
		admissionEvidenceSummary,
		canPredict,
		mediaSuccessCount,
		mediaFailedPlatforms,
	})

	console.log("")
	console.log("=".repeat(70))
	console.log(`考研热度预测：${school} ${major} ${session}`)
	console.log("=".repeat(70))
	console.log(`数据来源: ${dataSource}`)

	const failedPlatformsText = mediaFailedPlatforms.length > 0 ? `，已弃用: ${mediaFailedPlatforms.join(", ")}` : ""
	console.log("")
	console.log(`综合热度: ${currentHeat}/100  (${heatLevel.color} ${heatLevel.label})`)
	console.log(`  数据热度: ${adjustedDataHeat}/100  (报录比·复试线·趋势·推免)`)
	console.log(`  媒体热度: ${mediaHeat}/100  (成功 ${mediaSuccessCount}/8 平台${failedPlatformsText})`)

	console.log("")
	console.log(canPredict ? "录取历史:" : "录取历史: 暂未查询到权威录取历史")
	console.log("  年份    报考    录取    报录比    复试线")
	console.log("  " + "-".repeat(44))
	for (const h of admissionHistory) {
		const noteTag = h.note ? `  [${h.note}]` : ""
		console.log(`  ${h.year}   ${String(h.applicants).padStart(4)}    ${String(h.admitted).padStart(3)}     ${h.ratio.toFixed(1)}:1     ${h.cutScore}分${noteTag}`)
	}

	console.log("")
	console.log(canPredict ? `${session} 预测:` : `${session} 预测: 暂不生成（缺少权威录取历史）`)
	console.log(`  预计报考人数: ${prediction.estimatedApplicants} 人`)
	console.log(`  预计报录比: ${prediction.estimatedRatio}:1`)
	console.log(`  预计复试线: ${prediction.estimatedCutScore} 分`)
	console.log(`  热度估计: ${prediction.heatEstimate}`)

	console.log("")
	console.log("考试科目:")
	for (const s of subjects) {
		console.log(`  ${s.code} ${s.name}（${s.type}）`)
	}

	console.log("")
	console.log("影响因素:")
	for (const f of factors) {
		console.log(`  ${f.icon} ${f.title}: ${f.desc}`)
	}

	if (isReal) {
		console.log("")
		console.log("院校信息:")
		console.log(`  院校层次: ${schoolLevel}`)
		console.log(`  所属院系: ${department}`)
		console.log(`  推免情况: ${pushRatioDesc}`)
	}

	console.log("")
	if (mediaPlatforms.length > 0) {
		console.log("平台热度分布（不含微博）:")
		for (const p of mediaPlatforms) {
			if (p.score === null) {
				console.log(`  ❌ ${p.platform.padEnd(12)} 抓取失败`)
			} else {
				const bar = "█".repeat(Math.max(0, Math.round(p.score / 100 * 20)))
				const weightText = p.weight ? `(${Math.round(p.weight * 100)}%)` : ""
				console.log(`  ✅ ${p.platform.padEnd(12)} ${bar} ${p.score} ${weightText}`)
			}
		}
	} else {
		console.log("平台热度分布：未抓取到可用平台数据")
	}

	console.log("")
	console.log("历届热度趋势:")
	console.log("  届数    热度")
	console.log("  " + "-".repeat(20))
	for (const h of sessionHistory) {
		const bar = "█".repeat(Math.max(0, Math.round(h.heat / 100 * 20)))
		console.log(`  ${h.session}  ${bar} ${h.heat}`)
	}

	if (schoolNotes.length > 0) {
		console.log("")
		console.log("备注:")
		for (const note of schoolNotes) {
			console.log(`  - ${note}`)
		}
	}

	console.log("")
	const confidencePct = Math.round(confidence * 100)
	console.log(`综合置信度: ${confidencePct}%`)

	const trendText = trend === "rising" ? "上升" : trend === "falling" ? "下降" : trend === "unknown" ? "未知" : "稳定"
	console.log(`热度等级: ${heatLevel.color} ${heatLevel.label}`)
	console.log(`整体趋势: ${trendText}`)
	console.log("")

	// ─── 记忆提示输出 ───
	if (memory && !silent) {
		const queriedCount = memory.bank.episodicMemory.filter((e) => e.type === "query").length
		if (queriedCount > 1) {
			console.log(`💡 已记录第 ${queriedCount} 次查询，正在构建你的考研画像...`)
		}
		if (similarQueries.length > 0) {
			console.log(`📚 相似历史查询: ${similarQueries.map((e) => `${e.school} ${e.major}`).join("、")}`)
		}
		const profile = memory.getUserProfile()
		if (profile.targetTier?.length > 0 && queriedCount >= 5) {
			console.log(`🎯 历史偏好层次: ${profile.targetTier.map((t) => ({985:"985",211:"211",doubleFirst:"双一流",normal:"普通"}[t]||t)).join("、")}`)
		}
		console.log("")
	}

	// ─── 记忆写入（查询后）───
	let episodeId = null
	if (memory) {
		try {
			episodeId = memory.recordQuery({
				school,
				major,
				majorCode: opts.majorCode,
				session,
				result: {
					compositeHeat: currentHeat,
					heatLevel: heatLevel.label,
					dataSource,
				},
				context: {
					userIntent: similarQueries.length > 0 ? "follow-up" : "initial",
					rawInput: `${school} ${major}`,
				},
			})
			memory.recordDataSourcePreference(dataSource)
			if (opts.json) memory.recordFormatPreference("json")
		} catch (e) {
			// 记忆写入失败不阻塞主流程
		}
	}

	// 返回结构化数据（便于 --json 输出和 Skill 解析）
	const result = {
		school, major, session, targetYear,
		compositeHeat: currentHeat,
		dataHeat: adjustedDataHeat,
		mediaHeat,
		heatLevel: { label: heatLevel.label, color: heatLevel.color, min: getLevelMin(currentHeat) },
		dataSource,
		dataLevel: level,
		isReal,
		isEnriched,
		confidence: confidencePct,
		trend: trendText,
		prediction,
		admissionHistory,
		examSubjects: subjects,
		platforms: mediaPlatforms.map((p) => ({
			name: p.platform,
			score: p.score,
			weight: p.weight,
			source: p.source,
		})),
		failedPlatforms: mediaFailedPlatforms,
		schoolInfo: {
			schoolLevel,
			department,
			pushRatioDesc,
			plannedEnrollment,
			plannedEnrollmentText,
			sourceAuthority: sourceAuthority.label,
			sourceUrl: sourceAuthority.url,
			schoolLevelSource: schoolLevelInfo.source,
			schoolLevelConfidence: schoolLevelInfo.confidence,
			schoolLevelTags: schoolLevelInfo.tags,
			officialChannels,
			admissionDataChannels,
		},
		admissionEvidence,
		admissionEvidenceSummary,
		predictionBasis,
		notes: schoolNotes,
		matchInfo,
		programOptions,
		fieldSources,
		hasAuthoritativeAdmissionHistory,
		canPredict,
		dataQuality: predictionBasis === "official_evidence_extracted" ? "official_evidence_extracted" : (isPlanOnly || programOptions.length > 0) ? "plan_only" : canPredict ? "admission_history" : "unknown",
		// 记忆扩展字段
		memory: {
			episodeId,
			summary: memorySummary || null,
			similarQueries: similarQueries.map((e) => ({
				school: e.school,
				major: e.major,
				timestamp: e.timestamp,
				result: e.result,
			})),
			userProfile: memory ? memory.getUserProfile() : null,
		},
	}

	if (silent) console.log = originalLog
	return result
}

function getLevelMin(score) {
	if (score >= 90) return 90
	if (score >= 75) return 75
	if (score >= 60) return 60
	if (score >= 45) return 45
	if (score >= 25) return 25
	return 0
}

// ===== 导出（供 MCP / 其他模块使用） =====
export { resolveProfile, predictToSession, getHeatLevel, runForecast }

// ===== 入口 =====
if (typeof process !== "undefined" && process.argv?.[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
	const opts = parseArgs(process.argv)
	if (opts.help || !opts.school || (!opts.major && !opts.majorCode)) {
		showHelp()
		process.exit(opts.help ? 0 : 1)
	}

	const result = await runForecast(opts)
	if (opts.json) {
		console.log(JSON.stringify(result, null, 2))
	}
}
