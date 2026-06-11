// handebook-api.mjs — handebook.com Node.js API 客户端
// 签名算法: MD5(secret&appKey&timestamp&nonce&application&version&body_json).toUpperCase()

import { createHash, randomUUID } from "node:crypto"

const BASE_URL = "https://www.handebook.com"
const SECRET = "SV1dLfFDS32DS97jk32Qkjh34"
const APP_KEY = "202501018201"
const APPLICATION = "Pdfreader.Web"
const VERSION = "V2.3"

/**
 * 紧凑 JSON 序列化（无空格，不转义中文）
 * 必须与 Python 的 json.dumps(..., ensure_ascii=False, separators=(',', ':')) 一致
 */
function compactJson(obj) {
	if (obj === null) return "null"
	if (typeof obj === "boolean" || typeof obj === "number") return String(obj)
	if (typeof obj === "string") {
		let s = obj
			.replace(/\\/g, "\\\\")
			.replace(/"/g, '\\"')
			.replace(/\n/g, "\\n")
			.replace(/\r/g, "\\r")
			.replace(/\t/g, "\\t")
		// 注意：不转义 \b（正则单词边界）和 \f，正常文本中极少出现真正的退格/换页符
		return `"${s}"`
	}
	if (Array.isArray(obj)) {
		return "[" + obj.map(compactJson).join(",") + "]"
	}
	const pairs = []
	for (const key of Object.keys(obj)) {
		pairs.push(`${compactJson(key)}:${compactJson(obj[key])}`)
	}
	return "{" + pairs.join(",") + "}"
}

/**
 * 生成 API 请求签名
 */
function generateSign(bodyDict) {
	const timestamp = String(Math.floor(Date.now() / 1000))
	const nonce = randomUUID().toUpperCase()
	const bodyStr = compactJson(bodyDict)

	const raw = `${SECRET}&${APP_KEY}&${timestamp}&${nonce}&${APPLICATION}&${VERSION}&${bodyStr}`
	const sign = createHash("md5").update(raw, "utf-8").digest("hex").toUpperCase()

	return {
		headers: {
			"Content-Type": "application/json",
			"x-appkey": APP_KEY,
			"x-timestamp": timestamp,
			"x-nonce": nonce,
			"x-sign": sign,
			"x-application": APPLICATION,
			"x-version": VERSION,
		},
		bodyStr,
		raw,
	}
}

/**
 * 发送签名后的 POST 请求
 */
async function apiPost(endpoint, body, token = "null") {
	const { headers, bodyStr } = generateSign(body)
	if (token && token !== "null") {
		headers["x-token"] = token
	}

	const url = `${BASE_URL}${endpoint}`
	const resp = await fetch(url, {
		method: "POST",
		headers: {
			...headers,
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
			"Accept": "application/json, text/plain, */*",
			"Origin": "https://www.handebook.com",
			"Referer": "https://www.handebook.com/web/",
		},
		body: bodyStr,
	})

	if (!resp.ok) {
		return { Code: -1, Message: `HTTP ${resp.status}`, Success: false }
	}
	return resp.json()
}

// ═══════════════════════════════════════════════════════════
// 公开接口（无需登录）
// ═══════════════════════════════════════════════════════════

export async function getMajorList({ pageIndex = 1, pageSize = 50, universityCode = "", collegeCode = "", majorCode = "", majorLearningWay = "全日制" } = {}) {
	return apiPost("/api/web/admit/major/list", {
		universityCode,
		CollegeCode: collegeCode,
		MajorCode: majorCode,
		MajorLearningWay: majorLearningWay,
		PageIndex: pageIndex,
		PageSize: pageSize,
	})
}

export async function getMajorInfo(universityCode, collegeCode, majorCode, majorLearningWay = "全日制") {
	return apiPost("/api/web/admit/major/info", {
		universityCode,
		collegeCode,
		majorCode,
		majorLearningWay,
	})
}

export async function getSchoolInfo(universityCode, proxyCode = "18137782070") {
	return apiPost("/api/web/admit/school/info", {
		universityCode,
		proxyCode,
	})
}

export async function getCollegeInfo(universityCode, collegeCode) {
	return apiPost("/api/web/admit/college/info", {
		universityCode,
		collegeCode,
	})
}

// ═══════════════════════════════════════════════════════════
// VIP 接口（需要 token）
// ═══════════════════════════════════════════════════════════

export async function getAdmitList(universityCode, collegeCode, majorCode, { majorLearningWay = "全日制", admitYear = "2025", pageIndex = 1, pageSize = 50, token } = {}) {
	return apiPost("/api/web/admit/list", {
		universityCode,
		collegeCode,
		majorCode,
		majorLearningWay,
		admitYear,
		pageIndex,
		pageSize,
	}, token)
}

export async function getAdmitStatistic(universityCode, collegeCode, majorCode, { majorLearningWay = "全日制", admitYear = "2025", token } = {}) {
	return apiPost("/api/web/admit/statistic", {
		universityCode,
		collegeCode,
		majorCode,
		majorLearningWay,
		admitYear,
	}, token)
}

// ═══════════════════════════════════════════════════════════
// 认证接口
// ═══════════════════════════════════════════════════════════

export async function sendSms(phone) {
	return apiPost("/api/web/sms/common", { Phone: phone })
}

export async function login(phone, password, verifyCode, proxyCode = "18137782070") {
	return apiPost("/api/web/user/login", {
		UserPhone: phone,
		UserPassword: password,
		VerifyCode: verifyCode,
		ProxyCode: proxyCode,
	})
}

// ═══════════════════════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════════════════════

export async function getAllMajors({ majorLearningWay = "全日制", batchSize = 50 } = {}) {
	const allMajors = []
	let page = 1
	while (true) {
		const result = await getMajorList({ pageIndex: page, pageSize: batchSize, majorLearningWay })
		if (result.Code !== 1) {
			console.log(`[错误] 获取专业列表失败: ${result.Message}`)
			break
		}
		const majors = result.Data?.List || []
		if (!majors.length) break
		allMajors.push(...majors)
		const total = result.Data?.Count || 0
		if (total > 0 && allMajors.length >= total) break
		if (majors.length < batchSize) break
		page++
		await new Promise((r) => setTimeout(r, 500))
	}
	return allMajors
}

/**
 * 根据学校名称查找 universityCode（多页搜索）
 */
export async function findUniversityCode(schoolName) {
	for (let page = 1; ; page++) {
		const result = await getMajorList({ pageIndex: page, pageSize: 200 })
		if (result.Code !== 1) break
		const majors = result.Data?.List || []
		if (!majors.length) break
		for (const m of majors) {
			if (m.UniversityName?.includes(schoolName) || schoolName.includes(m.UniversityName)) {
				return m.UniversityCode
			}
		}
		if (majors.length < 200) break
	}
	return null
}

/**
 * 搜索指定学校的所有专业
 */
export async function searchSchoolMajors(schoolName) {
	const code = await findUniversityCode(schoolName)
	if (!code) return []
	const allMajors = await getAllMajors()
	return allMajors.filter((m) => m.UniversityCode === code || m.UniversityName?.includes(schoolName))
}

/**
 * 获取专业考试科目详情
 */
export async function fetchMajorSubjects(universityCode, collegeCode, majorCode, majorLearningWay = "全日制") {
	const info = await getMajorInfo(universityCode, collegeCode, majorCode, majorLearningWay)
	if (info.Code !== 1) return null
	const data = info.Data
	return {
		firstSubject: data?.MajorFirstSubject || "",   // 初试科目
		secondSubject: data?.MajorSecondSubject || "", // 复试科目
		firstExamBook: data?.MajorFirstExamBook || "",
		secondExamBook: data?.MajorSecondExamBook || "",
		plannedEnrollment: data?.MajorPlannedEnrollment || "",
		degreeType: data?.MajorDegreeType || "",
		researchDirection: data?.MajorResearchDirection || "",
		belongCategory: data?.MajorBelongcategory || "",
		belongFirstDiscipline: data?.MajorBelongFirstDiscipline || "",
	}
}

// CLI
if (import.meta.url === `file://${process.argv[1]}`) {
	const cmd = process.argv[2]
	if (cmd === "test") {
		// 测试公开接口：获取山东大学专业列表
		console.log("=== 测试 handebook 公开接口 ===")
		const majors = await searchSchoolMajors("山东大学")
		console.log(`找到 ${majors.length} 个专业`)
		for (const m of majors.slice(0, 5)) {
			console.log(`  ${m.MajorCode} ${m.MajorName} (${m.CollegeName}) 计划招生:${m.MajorPlannedEnrollment}`)
		}
		if (majors.length > 0) {
			const first = majors[0]
			console.log("\n=== 测试专业详情 ===")
			const detail = await fetchMajorSubjects(first.UniversityCode, first.CollegeCode, first.MajorCode, first.MajorLearningWay)
			console.log("初试科目:", detail.firstSubject)
			console.log("复试科目:", detail.secondSubject)
		}
	} else if (cmd === "all") {
		// 批量获取所有专业
		console.log("正在批量获取所有专业...")
		const all = await getAllMajors()
		console.log(`共获取 ${all.length} 个专业`)
		const fs = await import("node:fs")
		fs.writeFileSync("handebook_all_majors.json", JSON.stringify(all, null, 2))
		console.log("已保存到 handebook_all_majors.json")
	} else {
		console.log("handebook API 客户端")
		console.log("用法:")
		console.log("  node handebook-api.mjs test    # 测试公开接口")
		console.log("  node handebook-api.mjs all     # 批量获取所有专业")
	}
}
