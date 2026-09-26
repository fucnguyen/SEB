import os
import re
import io
import zipfile
import base64
from typing import Dict, Any, List, Optional

def read_7bit_int(b: bytes, pos: int):
    val = 0
    shift = 0
    while pos < len(b):
        byte = b[pos]
        pos += 1
        val |= (byte & 0x7f) << shift
        if (byte & 0x80) == 0:
            break
        shift += 7
    return val, pos

def is_valid_text(s: str) -> bool:
    if not s or len(s) < 2:
        return False
    printable = sum(1 for c in s if c.isprintable() or c in '\r\n\t')
    if (printable / len(s)) < 0.85:
        return False
    if any(k in s for k in ['PublicKeyToken', 'Culture=neutral', 'mscorlib', 'System.']):
        return False
    return True

def parse_nrbf_strings(raw: bytes) -> Dict[int, str]:
    """Trích xuất toàn bộ chuỗi BinaryObjectString (Record 0x06) hợp lệ theo ObjectId."""
    str_map = {}
    i = 0
    raw_len = len(raw)
    while i < raw_len - 6:
        if raw[i] == 0x06:
            obj_id = int.from_bytes(raw[i+1:i+5], 'little')
            # NRBF ObjectIds are sequential positive integers
            if 0 < obj_id < 10000:
                try:
                    length, str_pos = read_7bit_int(raw, i+5)
                    if 0 < length <= raw_len - str_pos and length < 30000:
                        s = raw[str_pos:str_pos+length].decode('utf-8', errors='ignore')
                        if is_valid_text(s):
                            str_map[obj_id] = s
                            i = str_pos + length
                            continue
                except Exception:
                    pass
        i += 1
    return str_map

def extract_pea_image(raw: bytes) -> Optional[bytes]:
    """Trích xuất ảnh đề thi thực hành PEA (JPEG) độ phân giải cao đầy đủ"""
    jpegs = [m.start() for m in re.finditer(rb'\xff\xd8\xff', raw)]
    for start in jpegs:
        end = raw.find(b'\xff\xd9', start)
        if end != -1 and end > start + 5000:
            return raw[start:end+2]
    return None

def extract_pea_starter_zip(raw: bytes) -> Optional[bytes]:
    """Trích xuất và đóng gói sạch sẽ Starter ZIP Project cho tất cả các câu hỏi (Q1, Q2, Q3, Q4) của đề PEA"""
    tasks_zips = []
    pos = 0
    raw_len = len(raw)

    # 1. Tìm các mảng byte GivenMaterials (Record 0x0F ArraySinglePrimitive kiểu byte 0x02)
    while pos < raw_len - 9:
        if raw[pos] == 0x0F and raw[pos+9] == 0x02:
            arr_len = int.from_bytes(raw[pos+5:pos+9], 'little')
            data_start = pos + 10
            if 500 < arr_len < 2000000 and data_start + arr_len <= raw_len:
                bdata = raw[data_start:data_start+arr_len]
                if bdata[:4] == b'PK\x03\x04':
                    try:
                        zf = zipfile.ZipFile(io.BytesIO(bdata))
                        if len(zf.namelist()) > 0:
                            tasks_zips.append(bdata)
                    except Exception:
                        pass
        pos += 1

    # 2. Nếu không tìm thấy qua cờ 0x0F, quét theo chữ ký PK\\x03\\x04
    if not tasks_zips:
        offsets = [m.start() for m in re.finditer(rb'PK\x03\x04', raw)]
        for off in offsets:
            try:
                sub_raw = raw[off:]
                zf = zipfile.ZipFile(io.BytesIO(sub_raw))
                if any('src/' in n for n in zf.namelist()) or len(zf.namelist()) >= 3:
                    tasks_zips.append(sub_raw)
                    break
            except Exception:
                pass

    if not tasks_zips:
        return None

    # 3. Đóng gói lại thành tệp ZIP chuẩn tuyệt đối không lỗi phần đuôi thừa
    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf_out:
        if len(tasks_zips) == 1:
            zf_in = zipfile.ZipFile(io.BytesIO(tasks_zips[0]))
            for item in zf_in.infolist():
                zf_out.writestr(item, zf_in.read(item.filename))
        else:
            for q_idx, q_zip in enumerate(tasks_zips):
                prefix = f"Q{q_idx+1}/"
                zf_in = zipfile.ZipFile(io.BytesIO(q_zip))
                for item in zf_in.infolist():
                    zf_out.writestr(prefix + item.filename, zf_in.read(item.filename))

    return out_buf.getvalue()

def parse_pea_exam(raw: bytes, filename: str) -> Dict[str, Any]:
    """Phân tích đề thi thực hành PEA (Java / C / C++ / C#)"""
    str_map = parse_nrbf_strings(raw)
    test_name = "TEST_PEA_PRACTICAL"
    language = "Java"

    for s in str_map.values():
        if "TEST_PEA" in s or "PEA" in s:
            test_name = s
        if s in ["Java", "C", "C++", "C#", "Python"]:
            language = s

    pea_img = extract_pea_image(raw)
    has_image = pea_img is not None

    task_specs = [
        ("Task 1 (2.0 điểm): Xây dựng lớp đối tượng & hàm xử lý chuỗi / định dạng (f1)",
         "Đọc kỹ yêu cầu đề bài trên ảnh đề thi PEA bên trên. Cài đặt các thuộc tính, hàm khởi tạo (Constructor) và hàm f1() theo đúng khuôn mẫu trong Starter ZIP đính kèm."),
        ("Task 2 (2.0 điểm): Cài đặt hàm xử lý chuỗi / thuật toán (f2)",
         "Đọc kỹ yêu cầu đề bài trên ảnh đề thi PEA bên trên. Cài đặt thuật toán xử lý dữ liệu của hàm f2() theo đúng định dạng kiểm thử."),
        ("Task 3 (3.0 điểm): Thao tác với cấu trúc danh sách & sắp xếp dữ liệu (f3)",
         "Đọc kỹ yêu cầu đề bài trên ảnh đề thi PEA bên trên. Cài đặt phương thức lọc/sắp xếp danh sách phần tử và trả về kết quả theo yêu cầu."),
        ("Task 4 (3.0 điểm): Hoàn thiện hàm nghiệp vụ tổng hợp & xuất kết quả (f4)",
         "Đọc kỹ yêu cầu đề bài trên ảnh đề thi PEA bên trên. Thực hiện kiểm thử toàn bộ các Test Case (TC1, TC2, TC3, TC4) trước khi nộp bài.")
    ]

    questions = []
    for q_idx in range(4):
        title, desc = task_specs[q_idx]
        questions.append({
            "question_index": q_idx,
            "question_type": "essay",
            "question_text": f"{title}\n\n{desc}",
            "options": [],
            "student_answer": "",
            "support_answer": "/* Bấm nút [Tạo Source PEA] trên thanh công cụ để tự động tạo và copy mã nguồn hoàn chỉnh vào Clipboard */"
        })

    return {
        "exam_title": f"PEA Practical ({language}): {test_name}",
        "language": language,
        "is_pea": True,
        "is_writing": False,
        "has_paper_image": has_image,
        "questions": questions
    }

def parse_writing_exam(raw: bytes, filename: str) -> Dict[str, Any]:
    """Phân tích đề thi tự luận / viết tiếng Anh EOS Writing"""
    str_map = parse_nrbf_strings(raw)
    exam_code = filename.replace('.dat', '').replace('.bin', '')
    for s in str_map.values():
        if re.match(r'^(TEST_PLT_W|W_)[A-Za-z0-9_]+', s):
            exam_code = s
            break

    prompt_b64 = ""
    pngs = [m.start() for m in re.finditer(rb'\x89PNG\r\n\x1a\n', raw)]
    for p in pngs:
        iend = raw.find(rb'IEND', p)
        if iend != -1:
            png_b = raw[p:iend+8]
            prompt_b64 = "data:image/png;base64," + base64.b64encode(png_b).decode()
            break

    questions = [{
        "question_index": 0,
        "question_type": "essay",
        "question_text": "Writing Task: Viết bài văn / luận tiếng Anh theo chủ đề và yêu cầu chi tiết trong hình ảnh đề thi bên dưới.",
        "image_base64": prompt_b64,
        "options": [],
        "student_answer": "",
        "support_answer": "/* Nhập bài văn tự luận mẫu hỗ trợ thí sinh tại đây */"
    }]

    return {
        "exam_title": f"EOS Tự Luận: {exam_code}",
        "language": "English",
        "is_pea": False,
        "is_writing": True,
        "has_paper_image": bool(prompt_b64),
        "questions": questions
    }

def parse_eos_exam(raw: bytes, filename: str) -> Dict[str, Any]:
    """Phân tích đề thi trắc nghiệm EOS chuẩn FPT (.dat / .bin)"""
    str_map = parse_nrbf_strings(raw)

    exam_code = ""
    for s in str_map.values():
        if re.match(r'^(TEST_|Test|MGT|PRF|PRO|PRJ|CSD|MAS|CSI|CEA|SSG|IAE)[A-Za-z0-9_]+', s):
            exam_code = s
            break
    if not exam_code:
        exam_code = filename.replace('.dat', '').replace('.bin', '')

    # Trích xuất danh sách đáp án theo qid
    answers_by_qid = {}
    pos = 0
    raw_len = len(raw)
    while pos < raw_len - 15:
        if raw[pos] in [0x06, 0x09] and pos >= 8:
            obj_id = int.from_bytes(raw[pos+1:pos+5], 'little')
            qaid = int.from_bytes(raw[pos-8:pos-4], 'little', signed=True)
            qid = int.from_bytes(raw[pos-4:pos], 'little', signed=True)
            if 0 < qaid < 500000 and 0 < qid < 50000:
                if obj_id in str_map:
                    ans_text = str_map[obj_id].strip()
                    if ans_text and ans_text not in ["PLT", "TEST_EOS", "Test 2"] and len(ans_text) > 0:
                        if qid not in answers_by_qid:
                            answers_by_qid[qid] = []
                        if not any(a == ans_text for a in answers_by_qid[qid]):
                            answers_by_qid[qid].append(ans_text)
        pos += 1

    # Trích xuất câu hỏi (stem)
    question_candidates = []
    ignore_stems = {"IRemote", "QuestionLib", "System.", "mscorlib", "FU88.cc", "TEST_EOS", "PLT", "Test 2"}

    for obj_id, s in str_map.items():
        s_clean = s.strip()
        if not s_clean or any(ig == s_clean for ig in ignore_stems):
            continue

        is_stem = (
            "(Choose" in s_clean or
            s_clean.startswith("PART") or
            s_clean.startswith("Read the text") or
            "?" in s_clean or
            "________" in s_clean or
            s_clean.startswith("Đối với") or
            s_clean.startswith("Trong phòng") or
            s_clean.startswith("Became ill") or
            s_clean.startswith("An important point") or
            s_clean.startswith("Hãy điền") or
            s_clean.startswith("CÁC THỦ TỤC")
        )

        if is_stem:
            is_ans = any(any(a == s_clean for a in alist) for alist in answers_by_qid.values())
            if not is_ans:
                display_stem = re.sub(r'^\(Choose\s+\d+\s+answer[s]?\)\s*', '', s_clean).strip()
                question_candidates.append(display_stem or s_clean)

    sorted_qids = sorted(answers_by_qid.keys())
    total_count = max(len(question_candidates), len(sorted_qids))
    if total_count == 0:
        total_count = 1
        question_candidates = ["Câu hỏi bài thi trắc nghiệm"]

    questions = []
    ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    for idx in range(total_count):
        stem = question_candidates[idx] if idx < len(question_candidates) else f"Câu hỏi trắc nghiệm số {idx+1}"
        matched_answers = answers_by_qid[sorted_qids[idx]] if idx < len(sorted_qids) else []

        options_obj = []
        for oi, ans in enumerate(matched_answers):
            lbl = ALPHA[oi] if oi < len(ALPHA) else str(oi+1)
            options_obj.append({"label": lbl, "text": ans, "image_base64": ""})

        q_type = "radio" if len(options_obj) > 1 else ("text" if not options_obj else "radio")
        questions.append({
            "question_index": idx,
            "question_type": q_type,
            "question_text": stem,
            "options": options_obj,
            "student_answer": "",
            "support_answer": ""
        })

    return {
        "exam_title": f"EOS Trắc Nghiệm: {exam_code}",
        "language": "General",
        "is_pea": False,
        "is_writing": False,
        "has_paper_image": False,
        "questions": questions
    }

def parse_full_exam_file(fp: str) -> Dict[str, Any]:
    """Điểm vào tổng hợp đọc và giải mã mọi tệp đề thi .dat/.bin (EOS & PEA)"""
    filename = os.path.basename(fp)
    with open(fp, "rb") as fh:
        raw = fh.read()

    is_pea = "PEA" in filename.upper() or b"IRemote.PEAData" in raw or b"PEAData" in raw[:500]
    if is_pea:
        return parse_pea_exam(raw, filename)

    is_writing = (b"TEST_PLT_W" in raw or b"_W_" in raw or "_W_" in filename.upper() or "WRITING" in filename.upper()) and not is_pea
    if is_writing:
        return parse_writing_exam(raw, filename)

    return parse_eos_exam(raw, filename)
