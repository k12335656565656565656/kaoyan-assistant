import unittest

from professional_knowledge.builtin_408 import BUILTIN_408_SOURCE_TYPE
from professional_knowledge.builtin_history import BUILTIN_HISTORY_SOURCE_TYPE
from services import professional_question_prompts as prompts
from services import professional_question_validator as validator
from services import true_exam_reference_service


class ProfessionalQuestionPromptTests(unittest.TestCase):
    def test_blank_prompt_requires_corresponding_non_conflicting_reference(self):
        point = {
            "knowledge_name": "最短路径算法",
            "subject": "数据结构",
            "source_type": BUILTIN_408_SOURCE_TYPE,
        }

        prompt = prompts.build_professional_question_prompt(point, mode="blank", variant=2)

        self.assertIn("reference_answer 必须逐空解释", prompt)
        self.assertIn("每个结论必须与 correct_answer 对应且不得矛盾", prompt)
        self.assertIn("不要考口径不唯一的交换次数", prompt)
        self.assertNotIn("完全一致", prompt)

    def test_408_shortest_path_blueprint_mentions_dijkstra_or_floyd(self):
        point = {
            "knowledge_name": "最短路径算法",
            "subject": "数据结构",
            "keywords_json": '["Dijkstra", "Floyd", "最短路径"]',
            "source_type": BUILTIN_408_SOURCE_TYPE,
        }

        blueprint = prompts.format_408_blueprints(point, mode="blank", variant=1)

        self.assertIn("408科目判定：数据结构", blueprint)
        self.assertTrue("Dijkstra" in blueprint or "Floyd" in blueprint)
        self.assertIn("可推演材料", blueprint)

    def test_408_blank_prompt_is_knowledge_cloze(self):
        point = {
            "knowledge_name": "快速排序",
            "subject": "数据结构",
            "keywords_json": '["快速排序", "时间复杂度", "稳定性"]',
            "source_type": BUILTIN_408_SOURCE_TYPE,
        }

        prompt = prompts.build_professional_question_prompt(point, mode="blank", variant=1)

        self.assertIn("知识点扣空填空题", prompt)
        self.assertIn("不强行综合推演", prompt)
        self.assertIn("40-140 字", prompt)

    def test_history_prompt_uses_true_exam_trends_and_grading_standard(self):
        point = {
            "knowledge_name": "东汉豪族",
            "subject": "历史学统考",
            "chapter_name": "中国古代史",
            "core_definition": "东汉地方豪族控制土地、宗族和地方政治。",
            "source_type": BUILTIN_HISTORY_SOURCE_TYPE,
        }

        prompt = prompts.build_professional_question_prompt(point, mode="algorithm", variant=1)

        self.assertIn("历年真题题型骨架", prompt)
        self.assertIn("主体内容30分+论述组织10分", prompt)
        self.assertIn("史实准确、史论结合、逻辑清楚、文字流畅", prompt)
        self.assertIn("313-2023-Q02", prompt)
        self.assertIn("证据等级A", prompt)

    def test_three_kingdoms_prompt_corrects_oversimplified_source_claim(self):
        point = {
            "knowledge_name": "三国鼎立",
            "subject": "历史学统考",
            "chapter_name": "中国古代史",
            "core_definition": "夷陵之战正式形成三国鼎立局面。",
            "source_type": BUILTIN_HISTORY_SOURCE_TYPE,
        }

        prompt = prompts.build_professional_question_prompt(
            point,
            mode="algorithm",
            variant=1,
        )

        self.assertIn("曹魏、蜀汉、孙吴分别于220、221、229年建立", prompt)
        self.assertIn("不得把它写成“三国鼎立正式形成”的唯一标志", prompt)
        self.assertNotIn("夷陵之战正式形成三国鼎立局面", prompt)

    def test_true_exam_retrieval_prefers_matching_subject_and_terms(self):
        point = {
            "knowledge_name": "线程信号量同步",
            "subject": "操作系统",
            "keywords_json": '["信号量", "线程同步", "前驱关系"]',
            "source_type": BUILTIN_408_SOURCE_TYPE,
        }

        items = true_exam_reference_service.select_true_exam_archetypes(
            point,
            "application",
            variant=1,
            limit=3,
        )

        self.assertTrue(items)
        self.assertEqual(items[0]["subject"], "操作系统")
        self.assertIn("信号量", items[0]["knowledge_terms"])

    def test_blank_is_explicitly_marked_as_true_exam_derived_review(self):
        point = {
            "knowledge_name": "快速排序",
            "subject": "数据结构",
            "source_type": BUILTIN_408_SOURCE_TYPE,
        }

        metadata = true_exam_reference_service.get_true_exam_reference_metadata(
            point,
            "blank",
        )

        self.assertEqual(metadata["derivation_type"], "true_exam_derived_review")
        self.assertIn("不是现行统考原生题型", metadata["evidence_notice"])


class ProfessionalQuestionValidatorTests(unittest.TestCase):
    def test_validator_accepts_valid_shortest_path_blank(self):
        generated = {
            "question_type": "blank",
            "question": "带权有向图从 A 到 D 的边有 A->B=2、A->C=6、B->D=3、C->D=1。先确定的中间顶点是 ______，A 到 D 的最短路径长度为 ______。",
            "options": [],
            "correct_answer": "B；5",
            "reference_answer": "第一空填 B，因为 Dijkstra 初始距离中 B 的距离 2 最小，应先确定 B。第二空填 5，经过 B 松弛后 A 到 D 的距离为 2+3=5，小于经 C 的 7。",
            "grading_points": ["先确定最小距离顶点", "完成松弛", "写出最短路径长度"],
        }

        self.assertTrue(
            validator.is_valid_professional_question_for_point(
                generated,
                "blank",
                {"knowledge_name": "最短路径算法", "subject": "数据结构"},
            )
        )

    def test_validator_rejects_contradictory_short_numeric_answer(self):
        generated = {
            "question_type": "blank",
            "question": "带权有向图从 A 到 D 的边有 A->B=2、A->C=6、B->D=3、C->D=1。A 到 D 的最短路径长度为 ______。",
            "options": [],
            "correct_answer": "7",
            "reference_answer": "空处填 5，因为 A->B->D 的路径长度为 2+3=5，小于 A->C->D 的 7。",
            "grading_points": ["完成松弛", "写出最短路径长度"],
        }

        self.assertFalse(
            validator.is_valid_professional_question_for_point(
                generated,
                "blank",
                {"knowledge_name": "最短路径算法", "subject": "数据结构"},
            )
        )

    def test_validator_accepts_parentheses_blank_marker(self):
        generated = {
            "question_type": "blank",
            "question": "在 Dijkstra 算法中，若存在负权边但无负权回路，应改用（ ）算法处理单源最短路径。",
            "options": [],
            "correct_answer": "Bellman-Ford",
            "reference_answer": "空处填 Bellman-Ford。Dijkstra 依赖每次确定的最短距离不会再变小，负权边会破坏这个性质；Bellman-Ford 通过多轮松弛处理含负权边的单源最短路径。",
            "grading_points": ["识别负权条件", "说明 Dijkstra 限制", "给出替代算法"],
        }

        self.assertEqual(validator.blank_marker_count(generated["question"]), 1)
        self.assertTrue(
            validator.is_valid_professional_question_for_point(
                generated,
                "blank",
                {"knowledge_name": "最短路径算法", "subject": "数据结构"},
            )
        )

    def test_validator_accepts_408_knowledge_cloze_blank(self):
        generated = {
            "question_type": "blank",
            "question": "快速排序平均时间复杂度为 ______，最坏时间复杂度为 ______，它属于 ______ 排序。",
            "options": [],
            "correct_answer": "O(nlogn)；O(n^2)；不稳定",
            "reference_answer": "第一空填 O(nlogn)，快速排序平均划分较均衡。第二空填 O(n^2)，划分极不均衡时退化。第三空填不稳定，因为相同关键字相对次序可能改变。",
            "grading_points": ["平均复杂度", "最坏复杂度", "稳定性"],
        }

        self.assertTrue(
            validator.is_valid_professional_question_for_point(
                generated,
                "blank",
                {"knowledge_name": "快速排序", "subject": "数据结构", "source_type": BUILTIN_408_SOURCE_TYPE},
            )
        )

    def test_validator_accepts_concise_history_discussion_question(self):
        generated = {
            "question_type": "algorithm",
            "question": "论述东汉豪族的主要特点及其对地方政治的影响。",
            "options": [],
            "correct_answer": "",
            "reference_answer": "东汉豪族以土地占有、宗族势力、经学门第和地方关系网络为基础，控制乡里社会并影响选官与地方治理。其发展削弱中央对基层的直接控制，推动地方政治家族化，也为魏晋门阀士族形成提供社会基础。",
            "grading_points": [
                "豪族形成与主要特点（15分）",
                "对地方政治的影响（15分）",
                "论述组织：史论结合、逻辑与文字表达（10分）",
            ],
        }

        self.assertTrue(
            validator.is_valid_professional_question_for_point(
                generated,
                "algorithm",
                {"knowledge_name": "东汉豪族", "subject": "历史学统考", "source_type": BUILTIN_HISTORY_SOURCE_TYPE},
            )
        )

    def test_validator_accepts_three_kingdoms_history_discussion_question(self):
        generated = {
            "question_type": "论述题",
            "question": "论述三国鼎立局面的形成过程及其历史影响。",
            "options": [],
            "correct_answer": "",
            "reference_answer": (
                "官渡之战为曹操统一北方奠定基础，赤壁之战阻止曹操统一全国，"
                "魏、蜀汉、吴政权相继建立，三方格局逐步确立。三国时期的区域治理"
                "推动了经济恢复与民族交往，也为此后的统一准备了条件。"
            ),
            "grading_points": [
                "形成过程与关键史实（15分）",
                "历史影响与统一趋势（15分）",
                "论述组织：史论结合、逻辑与文字表达（10分）",
            ],
        }

        self.assertTrue(
            validator.is_valid_professional_question_for_point(
                generated,
                "algorithm",
                {
                    "knowledge_name": "三国鼎立",
                    "subject": "历史学统考",
                    "source_type": BUILTIN_HISTORY_SOURCE_TYPE,
                },
            )
        )

    def test_validator_rejects_yiling_as_sole_formation_marker(self):
        generated = {
            "question_type": "论述题",
            "question": "论述三国鼎立局面的形成过程及其历史影响。",
            "options": [],
            "correct_answer": "",
            "reference_answer": "夷陵之战标志着形成三国鼎立，此后局势趋于稳定。",
            "grading_points": [
                "形成过程（15分）",
                "历史影响（15分）",
                "论述组织：史论结合、逻辑与文字表达（10分）",
            ],
        }

        self.assertFalse(
            validator.is_valid_professional_question_for_point(
                generated,
                "algorithm",
                {
                    "knowledge_name": "三国鼎立",
                    "subject": "历史学统考",
                    "source_type": BUILTIN_HISTORY_SOURCE_TYPE,
                },
            )
        )

    def test_validator_rejects_wrong_question_type(self):
        generated = {
            "question_type": "concept",
            "question": "论述东汉豪族的主要特点及其对地方政治的影响。",
            "options": [],
            "correct_answer": "",
            "reference_answer": "东汉豪族以土地、宗族和地方关系网络为基础，并影响地方治理。",
            "grading_points": ["豪族特点", "地方政治影响"],
        }

        self.assertFalse(
            validator.is_valid_professional_question_for_point(
                generated,
                "algorithm",
                {"knowledge_name": "东汉豪族", "subject": "历史学统考"},
            )
        )

    def test_validator_rejects_watermark_or_promotional_leakage(self):
        generated = {
            "question_type": "choice",
            "question": "2023年东汉豪族相关史实中，下列说法正确的是？关注公众号创梦资料。",
            "options": ["A. 土地", "B. 宗族", "C. 地方政治", "D. 以上均非"],
            "correct_answer": "C",
            "reference_answer": "C项正确，东汉豪族会影响地方政治；其余选项错误。",
            "grading_points": ["识别政治影响", "排除干扰项"],
        }

        self.assertFalse(
            validator.is_valid_professional_question_for_point(
                generated,
                "choice",
                {"knowledge_name": "东汉豪族", "subject": "历史学统考"},
            )
        )

    def test_validator_rejects_cache_replacement_while_set_has_free_way(self):
        generated = {
            "question_type": "application",
            "question": (
                "某机采用8路组相联Cache，初始为空。两个不同主存块均映射到第0组，"
                "请判断两次访问的缺失情况并说明装入过程。"
            ),
            "options": [],
            "correct_answer": "",
            "reference_answer": (
                "第一次缺失后第0组已有1个块。第二次缺失时按LRU替换此前块，"
                "再把新块填入另一路。"
            ),
            "grading_points": ["判断两次缺失", "说明组内装入过程"],
        }

        self.assertFalse(
            validator.is_valid_professional_question_for_point(
                generated,
                "application",
                {
                    "knowledge_name": "Cache组相联映射",
                    "subject": "计算机组成原理",
                    "source_type": BUILTIN_408_SOURCE_TYPE,
                },
            )
        )

    def test_validator_recalculates_cache_sequence_instead_of_trusting_answer(self):
        generated = {
            "question": (
                "某机的Cache容量为1KB，块大小为16B，采用4路组相联映射和LRU替换，"
                "初始为空。依次访问0x00000000、0x00000010、0x000000F0、"
                "0x00000100，判断每次访问是否命中。"
            ),
            "reference_answer": (
                "前三次访问均缺失。访问0x00000100时，组0中已有块0且Tag匹配，"
                "因此命中。总共1次命中、3次缺失。"
            ),
        }

        self.assertTrue(validator.cache_reference_has_calculation_conflict(generated))

    def test_validator_accepts_correct_cache_sequence_calculation(self):
        generated = {
            "question": (
                "某机的Cache容量为1KB，块大小为16B，采用4路组相联映射和LRU替换，"
                "初始为空。依次访问0x00000000、0x00000010、0x000000F0、"
                "0x00000100，判断每次访问是否命中。"
            ),
            "reference_answer": (
                "四次访问均缺失。0x00000100的组号仍为0，但Tag变为1，"
                "应装入组0的空闲路。总共0次命中、4次缺失。"
            ),
        }

        self.assertFalse(validator.cache_reference_has_calculation_conflict(generated))

    def test_validator_rejects_cache_sequence_without_initial_state(self):
        generated = {
            "question": (
                "某机采用直接映射Cache，Cache容量为1KB，块大小为64B。"
                "访问序列（块号）：0，8，0，8。统计命中和缺失次数。"
            ),
            "reference_answer": "命中2次，缺失2次。",
        }

        self.assertTrue(validator.cache_reference_has_calculation_conflict(generated))

    def test_validator_recalculates_direct_mapped_block_number_sequence(self):
        generated = {
            "question": (
                "某机采用直接映射Cache，Cache容量为1KB，块大小为64B，初始为空。"
                "访问序列（块号）：0，8，0，8。统计命中和缺失次数。"
            ),
            "reference_answer": "直接映射推演结果为命中0次、缺失4次。",
        }

        self.assertTrue(validator.cache_reference_has_calculation_conflict(generated))

    def test_validator_recalculates_decimal_cache_address_sequence(self):
        generated = {
            "question": (
                "某机Cache容量为1KB，块大小为16B，采用4路组相联和LRU，初始为空。"
                "访问以下主存地址（十进制）：0, 128, 256, 128, 512, 0, 256, "
                "1024, 128, 512, 0, 256, 1024, 2048, 0, 128。"
                "推演命中情况并统计命中与缺失次数。"
            ),
            "reference_answer": "总访问16次，命中8次，缺失8次。",
        }

        self.assertTrue(validator.cache_reference_has_calculation_conflict(generated))

    def test_validator_rejects_known_408_fact_conflict(self):
        generated = {
            "question_type": "blank",
            "question": "快速排序的平均时间复杂度为 ______，它属于 ______ 排序。",
            "options": [],
            "correct_answer": "O(n^3)；稳定",
            "reference_answer": "第一空填 O(n^3)，第二空填稳定排序。",
            "grading_points": ["平均复杂度", "稳定性"],
        }

        self.assertFalse(
            validator.is_valid_professional_question_for_point(
                generated,
                "blank",
                {"knowledge_name": "快速排序", "subject": "数据结构"},
            )
        )

    def test_validator_rejects_known_history_fact_conflict(self):
        generated = {
            "question_type": "choice",
            "question": "关于三省六部制，下列说法正确的是？",
            "options": [
                "A. 始建于明朝",
                "B. 三省职能完全相同",
                "C. 属于中央行政制度",
                "D. 与皇权无关",
            ],
            "correct_answer": "A",
            "reference_answer": "A项正确，三省六部制始建于明朝；其余选项错误。",
            "grading_points": ["判断制度时代", "辨析中央机构"],
        }

        self.assertFalse(
            validator.is_valid_professional_question_for_point(
                generated,
                "choice",
                {"knowledge_name": "三省六部制", "subject": "中国古代史"},
            )
        )


if __name__ == "__main__":
    unittest.main()
