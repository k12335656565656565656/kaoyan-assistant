// handebook-provider.mjs — handebook 数据提供者（优化版·带缓存）
// 公开接口：考试科目、招生人数、学位类型（免费）
// VIP 接口：录取名单、复试名单（需要 token）

import { getMajorList, getMajorInfo, getAdmitList, getAdmitStatistic } from "./handebook-api.mjs"
import { existsSync, readFileSync, writeFileSync } from "node:fs"
import { dirname } from "node:path"
import { fileURLToPath } from "node:url"

const AUTH_DIR = dirname(fileURLToPath(import.meta.url))
const CACHE_PATH = `${AUTH_DIR}/handebook-cache.json`
const CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000 // 7 天

function loadCache() {
	if (!existsSync(CACHE_PATH)) return { schools: {}, majors: {}, timestamp: 0 }
	try {
		return JSON.parse(readFileSync(CACHE_PATH, "utf-8"))
	} catch {
		return { schools: {}, majors: {}, timestamp: 0 }
	}
}

function saveCache(cache) {
	writeFileSync(CACHE_PATH, JSON.stringify(cache, null, 2))
}

function getCachedSchoolMajors(uniCode) {
	const cache = loadCache()
	const entry = cache.majors[uniCode]
	if (!entry) return null
	if (Date.now() - entry.timestamp > CACHE_TTL_MS) return null
	return entry.list
}

function setCachedSchoolMajors(uniCode, list) {
	const cache = loadCache()
	cache.majors[uniCode] = { timestamp: Date.now(), list }
	saveCache(cache)
}

function getCachedUniCode(schoolName) {
	const cache = loadCache()
	return cache.schools[schoolName] || null
}

function setCachedUniCode(schoolName, uniCode) {
	const cache = loadCache()
	cache.schools[schoolName] = uniCode
	saveCache(cache)
}

function normalize(str) {
	return String(str || "").replace(/\s+/g, "").toLowerCase()
}

function normalizeDegreeType(value) {
	const v = normalize(value)
	if (!v) return ""
	if (v === "academic" || v.includes("学硕") || v.includes("学术")) return "academic"
	if (v === "professional" || v.includes("专硕") || v.includes("专业")) return "professional"
	return ""
}

function inferDegreeTypeFromMajor(major) {
	const explicit = normalizeDegreeType(major?.MajorDegreeType)
	if (explicit) return explicit
	const code = String(major?.MajorCode || "")
	if (/^\d{6}$/.test(code) && code[2] === "5") return "professional"
	if (code) return "academic"
	return ""
}

function formatDegreeType(value) {
	const normalized = normalizeDegreeType(value)
	if (normalized === "academic") return "学硕"
	if (normalized === "professional") return "专硕"
	return value || "未确认"
}

function majorCodeMatches(candidateCode, requestedCode) {
	const candidate = String(candidateCode || "").trim()
	const requested = String(requestedCode || "").trim()
	if (!requested) return true
	if (!candidate) return false
	if (candidate === requested) return true
	return requested.length === 4 && candidate.startsWith(requested)
}

/**
 * 根据学校名称查找 universityCode（多页搜索 + 缓存）
 */
async function findUniversityCode(schoolName) {
	const cached = getCachedUniCode(schoolName)
	if (cached) return cached

	// 多页搜索，最多翻5页（覆盖所有高校）
	for (let page = 1; ; page++) {
		const result = await getMajorList({ pageIndex: page, pageSize: 200 })
		if (result.Code !== 1) break
		const majors = result.Data?.List || []
		if (!majors.length) break
		for (const m of majors) {
			if (m.UniversityName?.includes(schoolName) || schoolName.includes(m.UniversityName)) {
				setCachedUniCode(schoolName, m.UniversityCode)
				return m.UniversityCode
			}
		}
		// 200条都没找满说明已经是最后一页了
		if (majors.length < 200) break
	}
	return null
}

/**
 * 查找匹配学校的专业候选（关键优化：使用 universityCode 过滤）
 */
async function findMajors(schoolName, majorName, options = {}) {
	const uniCode = await findUniversityCode(schoolName)
	if (!uniCode) {
		console.log(`[Handebook] 未找到学校: ${schoolName}`)
		return []
	}
	const matchMode = options.matchMode === "exact" ? "exact" : "fuzzy"
	const requestedDegreeType = normalizeDegreeType(options.degreeType)
	const requestedMajorCode = String(options.majorCode || "").trim()

	// 先查缓存
	let majors = getCachedSchoolMajors(uniCode)
	if (!majors) {
		// 用 universityCode 过滤，只查该校专业（通常 1-3 页）
		majors = []
		let page = 1
		const batchSize = 50
		while (true) {
			const result = await getMajorList({ pageIndex: page, pageSize: batchSize, universityCode: uniCode })
			if (result.Code !== 1) break
			const list = result.Data?.List || []
			if (!list.length) break
			majors.push(...list)
			if (list.length < batchSize) break
			page++
			await new Promise((r) => setTimeout(r, 200))
		}
		setCachedSchoolMajors(uniCode, majors)
		console.log(`[Handebook] 缓存 ${schoolName} ${majors.length} 个专业`)
	} else {
		console.log(`[Handebook] 从缓存读取 ${schoolName} ${majors.length} 个专业`)
	}

	// 在缓存的专业列表中匹配
	const sName = normalize(majorName)
	const candidates = []
	for (const m of majors) {
		const mName = m.MajorName || ""
		const nm = normalize(mName)
		if (!majorCodeMatches(m.MajorCode, requestedMajorCode)) continue
		const currentDegreeType = inferDegreeTypeFromMajor(m)
		const degreeMatches = !requestedDegreeType || !currentDegreeType || currentDegreeType === requestedDegreeType
		if (!degreeMatches) continue

		const degreeRank = currentDegreeType === "academic" ? 2 : currentDegreeType === "professional" ? 1 : 0
		if (requestedMajorCode && !sName) {
			candidates.push({ score: 120, exactRank: 3, degreeRank, major: m })
		} else if (requestedMajorCode && (nm === sName || !sName)) {
			candidates.push({ score: 120, exactRank: 3, degreeRank, major: m })
		} else if (requestedMajorCode && matchMode === "fuzzy" && sName && (nm.includes(sName) || sName.includes(nm))) {
			candidates.push({ score: 110, exactRank: 2, degreeRank, major: m })
		} else if (nm === sName) {
			candidates.push({ score: 100, exactRank: 2, degreeRank, major: m })
		} else if (matchMode === "fuzzy" && sName && (nm.includes(sName) || sName.includes(nm))) {
			candidates.push({ score: nm.startsWith(sName) ? 80 : 60, exactRank: 1, degreeRank, major: m })
		}
	}
	candidates.sort((a, b) => {
		if (b.score !== a.score) return b.score - a.score
		if (!requestedDegreeType && b.exactRank !== a.exactRank) return b.exactRank - a.exactRank
		if (!requestedDegreeType && b.degreeRank !== a.degreeRank) return b.degreeRank - a.degreeRank
		const bPlan = Number(b.major.MajorPlannedEnrollment) || 0
		const aPlan = Number(a.major.MajorPlannedEnrollment) || 0
		return bPlan - aPlan
	})
	if (candidates.length > 0) return candidates.map((c) => c.major)

	console.log(`[Handebook] 未找到专业: ${schoolName} ${majorName}`)
	return []
}

async function findMajor(schoolName, majorName, options = {}) {
	const majors = await findMajors(schoolName, majorName, options)
	return majors[0] || null
}

/**
 * 解析考试科目文本为结构化数据
 */
function parseSubjects(text) {
	if (!text) return []
	const lines = text.split("\n").filter((l) => l.trim())
	const subjects = []
	for (const line of lines) {
		const match = line.match(/^([①②③④⑤⑥⑦⑧⑨⑩])(\d{3})\s*(.+)$/)
		if (match) {
			subjects.push({
				code: match[2],
				name: match[3].trim(),
				type: inferSubjectType(match[2], match[3]),
			})
		}
	}
	return subjects
}

function inferSubjectType(code, name) {
	if (code === "101") return "公共课"
	if (code.startsWith("2")) return "公共课" // 英语
	if (code.startsWith("3")) return "基础课" // 数学
	if (/政治|英语|数学/.test(name)) return "公共课"
	return "专业课"
}

/**
 * 将 handebook 专业记录转为页面可用 Profile。注意：这是招生计划补充数据，不是录取历史。
 */
async function buildHandebookProfile(major, options = {}) {
	const infoResult = await getMajorInfo(
		major.UniversityCode,
		major.CollegeCode,
		major.MajorCode,
		major.MajorLearningWay,
	)

	let examSubjects = []
	let firstSubject = ""
	let secondSubject = ""
	let plannedEnrollment = major.MajorPlannedEnrollment || ""
	let degreeType = major.MajorDegreeType || ""
	let researchDirection = ""

	if (infoResult.Code === 1 && infoResult.Data) {
		const d = infoResult.Data
		firstSubject = d.MajorFirstSubject || ""
		secondSubject = d.MajorSecondSubject || ""
		plannedEnrollment = d.MajorPlannedEnrollment || plannedEnrollment
		degreeType = d.MajorDegreeType || degreeType
		researchDirection = d.MajorResearchDirection || ""
		examSubjects = parseSubjects(firstSubject)
	}
	const normalizedDegreeType = normalizeDegreeType(degreeType)
	const requestedDegreeType = normalizeDegreeType(options.degreeType)
	if (requestedDegreeType && normalizedDegreeType !== requestedDegreeType) {
		console.log(`[Handebook] 学位类型不匹配: ${formatDegreeType(degreeType)} != ${formatDegreeType(requestedDegreeType)}`)
		return null
	}
	const planNumber = Number(plannedEnrollment) || null
	const projectLabel = [
		major.CollegeName,
		major.MajorName,
		researchDirection,
	].filter(Boolean).join(" · ")

	const profile = {
		school: major.UniversityName,
		universityCode: major.UniversityCode,
		major: major.MajorName,
		majorCode: major.MajorCode,
		degreeType: normalizedDegreeType || degreeType,
		degreeTypeLabel: formatDegreeType(degreeType),
		schoolLevel: inferSchoolLevel(major.UniversityPartition),
		department: major.CollegeName,
		learningWay: major.MajorLearningWay || "",
		plannedEnrollment: planNumber,
		plannedEnrollmentText: plannedEnrollment ? `${plannedEnrollment} 人` : "未公布",
		researchDirection,
		projectLabel,
		examSubjects: examSubjects.length > 0 ? examSubjects : generateDefaultSubjects(major.MajorName),
		history: [],
		notes: [
			"补充来源：handebook 公开接口（仅用于考试科目、计划招生字段；录取人数、推免比例、复试线需以招生单位官网/研招网为准）",
			`计划招生：${plannedEnrollment || "未公布"}`,
			`学位类型：${formatDegreeType(degreeType)}`,
			`院系/方向：${[major.CollegeName, researchDirection].filter(Boolean).join(" · ") || "未公布"}`,
			firstSubject ? `初试科目：${firstSubject.replace(/\n/g, " | ")}` : "初试科目：未查询到",
		],
		source: "handebook_supplement",
		sourceKind: "plan_only",
		hasAuthoritativeAdmissionHistory: false,
	}

	return profile
}

function dedupeProfiles(profiles) {
	const seen = new Set()
	const result = []
	for (const profile of profiles) {
		const key = [
			profile.school,
			profile.department,
			profile.majorCode,
			profile.major,
			profile.degreeType,
			profile.learningWay,
			profile.plannedEnrollmentText,
			profile.researchDirection,
		].join("::")
		if (seen.has(key)) continue
		seen.add(key)
		result.push(profile)
	}
	return result
}

function sortProfiles(profiles) {
	return [...profiles].sort((a, b) => {
		const bPlan = Number(b.plannedEnrollment) || 0
		const aPlan = Number(a.plannedEnrollment) || 0
		if (bPlan !== aPlan) return bPlan - aPlan
		return String(a.department || "").localeCompare(String(b.department || ""), "zh-Hans-CN")
	})
}

function toProgramOption(profile, index) {
	return {
		index,
		school: profile.school,
		universityCode: profile.universityCode,
		department: profile.department,
		major: profile.major,
		majorCode: profile.majorCode,
		degreeType: profile.degreeType,
		degreeTypeLabel: profile.degreeTypeLabel,
		learningWay: profile.learningWay,
		plannedEnrollment: profile.plannedEnrollment,
		plannedEnrollmentText: profile.plannedEnrollmentText,
		researchDirection: profile.researchDirection,
		projectLabel: profile.projectLabel,
		examSubjects: profile.examSubjects,
		sourceKind: profile.sourceKind,
	}
}

/**
 * 获取 handebook 公开数据候选（考试科目、招生计划等补充字段）
 */
export async function fetchHandebookProfiles(schoolName, majorName, options = {}) {
	console.log(`[Handebook] 查询 ${schoolName} ${majorName} ...`)

	const majors = await findMajors(schoolName, majorName, options)
	if (!majors.length) return []

	const profiles = []
	for (const major of majors) {
		console.log(`[Handebook] 候选: ${major.MajorName} (${major.MajorCode}) ${major.CollegeName} 招生:${major.MajorPlannedEnrollment}`)
		const profile = await buildHandebookProfile(major, options)
		if (profile) profiles.push(profile)
		await new Promise((r) => setTimeout(r, 100))
	}

	return dedupeProfiles(profiles)
}

/**
 * 获取 handebook 公开数据（考试科目、招生人数等）
 */
export async function fetchHandebookProfile(schoolName, majorName, options = {}) {
	const profiles = await fetchHandebookProfiles(schoolName, majorName, options)
	if (!profiles.length) return null
	const primary = profiles[0]
	primary.programOptions = profiles.map(toProgramOption)
	return primary
}

/**
 * 使用 VIP token 获取录取数据
 */
export async function fetchHandebookAdmitData(schoolName, majorName, admitYear = "2025", token = null) {
	if (!token) return null

	const major = await findMajor(schoolName, majorName)
	if (!major) return null

	console.log(`[Handebook VIP] 查询 ${schoolName} ${majorName} ${admitYear} 录取数据...`)

	// 录取名单
	const admitResult = await getAdmitList(
		major.UniversityCode,
		major.CollegeCode,
		major.MajorCode,
		{ admitYear, token },
	)

	// 录取统计
	const statResult = await getAdmitStatistic(
		major.UniversityCode,
		major.CollegeCode,
		major.MajorCode,
		{ admitYear, token },
	)

	return {
		admitList: admitResult.Data?.List || [],
		statistic: statResult.Data || null,
	}
}

function inferSchoolLevel(partition) {
	// handebook 的 Partition 是招生批次（A=本科一批 B=本科二批），不是985/211
	// 无法从 handebook 数据推断学校层次，统一返回待确认
	return "未确认"
}

function generateDefaultSubjects(major) {
	// fallback 默认科目
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

// CLI
if (import.meta.url === `file://${process.argv[1]}`) {
	const school = process.argv[2] || "山东大学"
	const major = process.argv[3] || "俄语笔译"
	const token = process.argv[4] || null

	const profile = await fetchHandebookProfile(school, major)
	if (profile) {
		console.log("\n=== Profile ===")
		console.log(JSON.stringify(profile, null, 2))
	}

	if (token) {
		const vip = await fetchHandebookAdmitData(school, major, "2025", token)
		if (vip) {
			console.log("\n=== VIP 录取数据 ===")
			console.log("录取人数:", vip.admitList.length)
			console.log("统计:", JSON.stringify(vip.statistic, null, 2))
		}
	}
}
