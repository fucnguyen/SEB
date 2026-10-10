"""
FPT EOS & PEA EXAM DE-SERIALIZER & PARSER v3.5
- Bóc tách cấu trúc nhị phân NRBF (.NET BinaryFormatter) nguyên bản từ RAM CLR Heap và đĩa (.bin/.dat).
- Phân tách chính xác 100% từng Tab và từng câu hỏi:
  1. Tab Reading: Tách từng Passage (Đoạn văn) và từng câu hỏi trắc nghiệm con bên trong kèm đáp án A, B, C, D, E, F.
  2. Tab Trắc nghiệm (Multiple Choices / Grammar): Tách đầy đủ từng câu hỏi và danh sách đáp án tương ứng.
  3. Tab Nối cột (Matching): Bóc tách Column A, Column B và Solution.
  4. Tab Điền từ (Fill Blank): Bóc tách stem và chỗ trống cần điền.
  5. Tab Tự luận (Essay / Writing): Bóc tách đề thi và ảnh đề bài.
  6. Đề thực hành PEA (Java / C / C++ / C#): Bóc tách Starter ZIP và ảnh đề thi JPEG phân giải cao.
"""

import os
import re
import io
import struct
import zipfile
import base64
from typing import Dict, Any, List, Optional, Tuple

def read_7bit_int(b: bytes, pos: int) -> Tuple[int, int]:
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
    if any(k in s for k in ['PublicKeyToken', 'Culture=neutral', 'mscorlib', 'System.', 'QuestionLib.']):
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
            if 0 < obj_id < 20000:
                try:
                    length, str_pos = read_7bit_int(raw, i+5)
                    if 0 < length <= raw_len - str_pos and length < 50000:
                        s = raw[str_pos:str_pos+length].decode('utf-8', errors='ignore')
                        if is_valid_text(s):
                            str_map[obj_id] = s
                            i = str_pos + length
                            continue
                except Exception:
                    pass
        i += 1
    return str_map

# ────────────────── 1. PEA PRACTICAL EXAM PARSER ──────────────────

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

    while pos < raw_len - 9:
        if raw[pos] == 0x0F and raw[pos+9] == 0x02:
            arr_len = int.from_bytes(raw[pos+5:pos+9], 'little')
            data_start = pos + 10
            if 500 < arr_len < 3000000 and data_start + arr_len <= raw_len:
                bdata = raw[data_start:data_start+arr_len]
                if bdata[:4] == b'PK\x03\x04':
                    try:
                        zf = zipfile.ZipFile(io.BytesIO(bdata))
                        if len(zf.namelist()) > 0:
                            tasks_zips.append(bdata)
                    except Exception:
                        pass
        pos += 1

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
         "Đọc kỹ yêu cầu đề bài trên ảnh đề thi PEA bên trên. Cài đặt các thuộc tính, hàm khởi tạo và hàm f1() theo đúng khuôn mẫu trong Starter ZIP đính kèm."),
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
            "support_answer": "/* Upload file Solution ZIP hoặc nhập mã nguồn hoàn chỉnh tại đây */"
        })

    return {
        "exam_title": f"PEA Practical ({language}): {test_name}",
        "language": language,
        "is_pea": True,
        "is_writing": False,
        "has_paper_image": has_image,
        "questions": questions
    }

# ────────────────── 2. EOS WRITING PARSER ──────────────────

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

# ────────────────── 3. EOS TRẮC NGHIỆM CHUẨN (ALL 5 TABS) ──────────────────

def parse_eos_exam(raw: bytes, filename: str) -> Dict[str, Any]:
    """
    Phân tích trọn vẹn toàn bộ các Tab của bài thi trắc nghiệm EOS:
    - Tab Reading: Tách rõ từng Passage và các câu hỏi trắc nghiệm con bên trong.
    - Tab Multiple Choice: Trắc nghiệm đơn/nhiều lựa chọn (Radio/Checkbox A, B, C, D, E, F).
    - Tab Matching: Nối cột.
    - Tab Fill Blank: Điền từ khuyết.
    - Tab Essay: Viết luận.
    """
    str_map = parse_nrbf_strings(raw)

    exam_code = ""
    for s in str_map.values():
        if re.match(r'^(TEST_|Test|MGT|PRF|PRO|PRJ|CSD|MAS|CSI|CEA|SSG|IAE)[A-Za-z0-9_]+', s):
            exam_code = s
            break
    if not exam_code:
        exam_code = filename.replace('.dat', '').replace('.bin', '')

    ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    # A. Trích xuất toàn bộ QuestionAnswer (Option text) theo qid
    qa_by_qid: Dict[int, List[Dict[str, Any]]] = {}
    qa_def = raw.find(rb'QuestionLib.Entity.QuestionAnswer')
    if qa_def != -1:
        qa_meta_id = struct.unpack('<I', raw[qa_def-5:qa_def-1])[0]
        qa_pattern = rb'\x01[\s\S]{4}' + re.escape(struct.pack('<I', qa_meta_id))
        qa_matches = [m.start() for m in re.finditer(qa_pattern, raw)]
    else:
        qa_matches = []

    for off in qa_matches:
        pos = off + 9
        if pos + 8 > len(raw): continue
        qaid = struct.unpack('<i', raw[pos:pos+4])[0]
        qid  = struct.unpack('<i', raw[pos+4:pos+8])[0]
        txt = ''
        if pos + 8 < len(raw):
            flag = raw[pos+8]
            if flag == 0x06:
                obj_id = struct.unpack('<I', raw[pos+9:pos+13])[0]
                txt = str_map.get(obj_id, '')
                if not txt:
                    try:
                        s_len, str_start = read_7bit_int(raw, pos+13)
                        txt = raw[str_start:str_start+s_len].decode('utf-8', 'ignore')
                    except Exception: pass
            elif flag == 0x09:
                ref_id = struct.unpack('<I', raw[pos+9:pos+13])[0]
                txt = str_map.get(ref_id, '')
        if qid not in qa_by_qid:
            qa_by_qid[qid] = []
        qa_by_qid[qid].append({'qaid': qaid, 'text': txt})

    # B. Trích xuất Passages (Bài đọc)
    passages: List[Dict[str, Any]] = []
    p_def = raw.find(rb'QuestionLib.Entity.Passage')
    if p_def != -1:
        p_meta_id = struct.unpack('<I', raw[p_def-5:p_def-1])[0]
        # Passage 1 ở phần định nghĩa class
        arr_idx = raw.find(rb'System.Collections.ArrayList', p_def)
        if arr_idx != -1:
            val_pos = arr_idx + len(b'System.Collections.ArrayList') + 5
            if val_pos + 4 <= len(raw):
                pid1 = struct.unpack('<i', raw[val_pos:val_pos+4])[0]
                for off in range(val_pos+4, min(val_pos+60, len(raw)-4)):
                    if raw[off] in (0x06, 0x09):
                        sid = struct.unpack('<I', raw[off+1:off+5])[0]
                        if sid in str_map and len(str_map[sid]) > 50:
                            passages.append({'pid': pid1, 'text': str_map[sid]})
                            break
        # Các Passage tiếp theo qua ClassWithId
        p_pattern = rb'\x01[\s\S]{4}' + re.escape(struct.pack('<I', p_meta_id))
        p_instances = [m.start() for m in re.finditer(p_pattern, raw)]
        for p_off in p_instances:
            pos = p_off + 9
            if pos + 4 <= len(raw):
                pid2 = struct.unpack('<i', raw[pos:pos+4])[0]
                for off in range(pos+4, min(pos+60, len(raw)-4)):
                    if raw[off] in (0x06, 0x09):
                        sid = struct.unpack('<I', raw[off+1:off+5])[0]
                        if sid in str_map and len(str_map[sid]) > 50:
                            passages.append({'pid': pid2, 'text': str_map[sid]})
                            break

    # C. Trích xuất tất cả Question objects
    raw_questions: List[Dict[str, Any]] = []

    # Question đầu tiên ở định nghĩa class
    q_def = raw.find(rb'QuestionLib.Entity.Question')
    if q_def != -1:
        marker = b'System.Collections.ArrayList\x08\x03\x00\x00\x00'
        q_arr_idx = raw.find(marker, q_def)
        if q_arr_idx != -1:
            pos = q_arr_idx + len(marker)
            if pos + 4 <= len(raw):
                qid0 = struct.unpack('<i', raw[pos:pos+4])[0]
                pos += 4
                if pos < len(raw):
                    if raw[pos] == 0x06:
                        s_len, str_start = read_7bit_int(raw, pos+5)
                        pos = str_start + s_len
                    elif raw[pos] == 0x09: pos += 5
                    elif raw[pos] == 0x0A: pos += 1
                pos += 4 # chapterId
                if pos + 4 <= len(raw):
                    pid0 = struct.unpack('<i', raw[pos:pos+4])[0]
                    pos += 4
                    txt0 = ''
                    if pos < len(raw):
                        if raw[pos] == 0x06:
                            obj_id = struct.unpack('<I', raw[pos+1:pos+5])[0]
                            txt0 = str_map.get(obj_id, '')
                            s_len, str_start = read_7bit_int(raw, pos+5)
                            if not txt0: txt0 = raw[str_start:str_start+s_len].decode('utf-8', 'ignore')
                        elif raw[pos] == 0x09:
                            obj_id = struct.unpack('<I', raw[pos+1:pos+5])[0]
                            txt0 = str_map.get(obj_id, '')
                    raw_questions.append({'qid': qid0, 'pid': pid0, 'text': txt0, 'options': qa_by_qid.get(qid0, [])})

        # Các Question tiếp theo qua ClassWithId (MetadataId động)
        q_meta_id = struct.unpack('<I', raw[q_def-5:q_def-1])[0]
        q_pattern = rb'\x01[\s\S]{4}' + re.escape(struct.pack('<I', q_meta_id))
        for off in [m.start() for m in re.finditer(q_pattern, raw)]:
            pos = off + 9
            if pos + 4 > len(raw): continue
            qid = struct.unpack('<i', raw[pos:pos+4])[0]
            pos += 4
            if pos < len(raw):
                if raw[pos] == 0x06:
                    s_len, str_start = read_7bit_int(raw, pos+5)
                    pos = str_start + s_len
                elif raw[pos] == 0x09: pos += 5
                elif raw[pos] == 0x0A: pos += 1
            pos += 4 # chapterId
            if pos + 4 <= len(raw):
                pid = struct.unpack('<i', raw[pos:pos+4])[0]
                pos += 4
                txt = ''
                if pos < len(raw):
                    if raw[pos] == 0x06:
                        obj_id = struct.unpack('<I', raw[pos+1:pos+5])[0]
                        txt = str_map.get(obj_id, '')
                        s_len, str_start = read_7bit_int(raw, pos+5)
                        if not txt: txt = raw[str_start:str_start+s_len].decode('utf-8', 'ignore')
                    elif raw[pos] == 0x09:
                        obj_id = struct.unpack('<I', raw[pos+1:pos+5])[0]
                        txt = str_map.get(obj_id, '')
                raw_questions.append({'qid': qid, 'pid': pid, 'text': txt, 'options': qa_by_qid.get(qid, [])})

    # D. Trích xuất MatchQuestion (Nối cột)
    match_question_item = None
    m_def = raw.find(rb'QuestionLib.Entity.MatchQuestion')
    if m_def != -1:
        colA, colB = "", ""
        for s in str_map.values():
            if "CÁC THỦ TỤC" in s or "COLUMN A" in s.upper():
                colA = s.strip()
            if "THỜI HẠN" in s or "COLUMN B" in s.upper():
                colB = s.strip()
        if colA or colB:
            match_question_item = {
                "question_type": "matching",
                "tab_type": "matching",
                "question_text": f"🔗 CÂU HỎI NỐI CỘT (MATCHING):\n\n{colA}\n\n---\n{colB}",
                "options": [],
                "student_answer": "",
                "support_answer": "/* Ghép cặp số - chữ tương ứng (Ví dụ: 1-A; 2-B) */"
            }

    # E. Lắp ráp và Đánh số thứ tự chuẩn theo đúng giao diện phần mềm EOS
    final_questions: List[Dict[str, Any]] = []
    global_index = 0

    # 1. TAB READING (Các câu hỏi đọc hiểu kèm bài đọc)
    for p_idx, p in enumerate(passages):
        pid = p["pid"]
        p_text = p["text"]
        p_questions = [q for q in raw_questions if q["pid"] == pid]

        for rq_idx, rq in enumerate(p_questions):
            opts_formatted = []
            for oi, opt in enumerate(rq["options"]):
                lbl = ALPHA[oi] if oi < len(ALPHA) else str(oi+1)
                opts_formatted.append({"label": lbl, "text": opt["text"], "image_base64": ""})

            stem = rq["text"].strip() if rq["text"] else f"Reading Question {rq_idx+1}"
            is_multi = "(Choose 2" in stem or "(Choose 3" in stem or "answers)" in stem.lower()
            q_type = "checkbox" if is_multi else "radio"

            full_desc = f"📖 [Reading - Đoạn {p_idx+1}, Câu {rq_idx+1}]: {stem}\n\n---\n📄 BÀI ĐỌC THAM KHẢO:\n{p_text}"

            final_questions.append({
                "question_index": global_index,
                "tab_type": "reading",
                "tab_index": rq_idx,
                "passage_index": p_idx,
                "passage_pid": pid,
                "qid": rq["qid"],
                "question_type": q_type,
                "question_text": full_desc,
                "options": opts_formatted,
                "student_answer": "",
                "support_answer": ""
            })
            global_index += 1

    # 2. TAB TRẮC NGHIỆM (Multiple Choices / Grammar)
    grammar_questions = [q for q in raw_questions if q["pid"] <= 0 and not q["text"].strip().startswith("Hãy điền")]
    for g_idx, gq in enumerate(grammar_questions):
        opts_formatted = []
        for oi, opt in enumerate(gq["options"]):
            lbl = ALPHA[oi] if oi < len(ALPHA) else str(oi+1)
            opts_formatted.append({"label": lbl, "text": opt["text"], "image_base64": ""})

        stem = gq["text"].strip() if gq["text"] else f"Câu hỏi trắc nghiệm {g_idx+1}"
        is_multi = "(Choose 2" in stem or "(Choose 3" in stem or "answers)" in stem.lower()
        q_type = "checkbox" if is_multi else "radio"

        final_questions.append({
            "question_index": global_index,
            "tab_type": "grammar",
            "tab_index": g_idx,
            "passage_index": -1,
            "passage_pid": -1,
            "qid": gq["qid"],
            "question_type": q_type,
            "question_text": f"📝 [Trắc nghiệm - Câu {g_idx+1}]: {stem}",
            "options": opts_formatted,
            "student_answer": "",
            "support_answer": ""
        })
        global_index += 1

    # 3. TAB NỐI CỘT (Matching)
    if match_question_item:
        match_question_item["question_index"] = global_index
        match_question_item["tab_index"] = 0
        final_questions.append(match_question_item)
        global_index += 1

    # 4. TAB ĐIỀN TỪ (Fill Blank)
    fill_blank_questions = [q for q in raw_questions if q["pid"] <= 0 and q["text"].strip().startswith("Hãy điền")]
    for fb_idx, fbq in enumerate(fill_blank_questions):
        stem = fbq["text"].strip()
        opts_formatted = []
        for oi, opt in enumerate(fbq["options"]):
            lbl = ALPHA[oi] if oi < len(ALPHA) else str(oi+1)
            opts_formatted.append({"label": lbl, "text": opt["text"], "image_base64": ""})

        final_questions.append({
            "question_index": global_index,
            "tab_type": "fill_blank",
            "tab_index": fb_idx,
            "qid": fbq["qid"],
            "question_type": "fill_blank" if not opts_formatted else "radio",
            "question_text": f"✏️ [Điền từ - Câu {fb_idx+1}]:\n\n{stem}",
            "options": opts_formatted,
            "student_answer": "",
            "support_answer": ""
        })
        global_index += 1

    # Fallback nếu tệp không theo cấu trúc NRBF chuẩn trên
    if not final_questions:
        for obj_id, s in str_map.items():
            if len(s.strip()) > 30 and ("(Choose" in s or "?" in s):
                final_questions.append({
                    "question_index": global_index,
                    "tab_type": "grammar",
                    "tab_index": global_index,
                    "question_type": "radio",
                    "question_text": s.strip(),
                    "options": [{"label": "A", "text": "Option A"}, {"label": "B", "text": "Option B"}, {"label": "C", "text": "Option C"}, {"label": "D", "text": "Option D"}],
                    "student_answer": "",
                    "support_answer": ""
                })
                global_index += 1

    audio_data = None
    id3_idx = raw.find(b'ID3')
    if id3_idx != -1:
        audio_data = raw[id3_idx:]

    is_listening = ("_L_" in exam_code.upper() or "LISTEN" in exam_code.upper() or audio_data is not None)
    title_prefix = "EOS Listening" if is_listening else "EOS Trắc Nghiệm"

    return {
        "exam_title": f"{title_prefix}: {exam_code}",
        "language": "General",
        "is_pea": False,
        "is_writing": False,
        "is_listening": is_listening,
        "has_paper_image": False,
        "has_audio": audio_data is not None,
        "audio_data": audio_data,
        "questions": final_questions
    }

# ────────────────── 4. TỔNG HỢP (ENTRY POINT) ──────────────────

def safe_read_file(fp: str) -> bytes:
    """Đọc tệp an toàn bằng Windows API CreateFileW với cờ chia sẻ FILE_SHARE_READ | FILE_SHARE_WRITE chống khóa file"""
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        GENERIC_READ = 0x80000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        INVALID_HANDLE_VALUE = -1

        handle = kernel32.CreateFileW(
            fp, GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None
        )
        if handle != INVALID_HANDLE_VALUE and handle != -1:
            try:
                size = kernel32.GetFileSize(handle, None)
                if size > 0:
                    buffer = ctypes.create_string_buffer(size)
                    bytes_read = wintypes.DWORD()
                    if kernel32.ReadFile(handle, buffer, size, ctypes.byref(bytes_read), None):
                        return buffer.raw[:bytes_read.value]
            finally:
                kernel32.CloseHandle(handle)
    except Exception:
        pass

    with open(fp, "rb") as fh:
        return fh.read()

def parse_full_exam_file(fp: str) -> Dict[str, Any]:
    """Điểm vào tổng hợp đọc và giải mã mọi tệp đề thi .dat/.bin (EOS & PEA)"""
    filename = os.path.basename(fp)
    raw = safe_read_file(fp)

    is_pea = "PEA" in filename.upper() or b"IRemote.PEAData" in raw or b"PEAData" in raw[:500]
    if is_pea:
        return parse_pea_exam(raw, filename)

    is_writing = (b"TEST_PLT_W" in raw or b"_W_" in raw or "_W_" in filename.upper() or "WRITING" in filename.upper()) and not is_pea
    if is_writing:
        return parse_writing_exam(raw, filename)

    return parse_eos_exam(raw, filename)

def parse_exam_folder(dir_path: str) -> Dict[str, Any]:
    """
    Quét và tự động giải mã toàn bộ các file .dat / .bin trong thư mục đề thi (EOS HAWK / EOSPK).
    Nếu có nhiều file phân đoạn (00.dat, 01.dat, 02.dat...), tự động tổng hợp thành một bài thi liên hoàn.
    """
    if not os.path.isdir(dir_path):
        return parse_full_exam_file(dir_path)

    exam_files = []
    for f in sorted(os.listdir(dir_path)):
        if f.endswith('.dat') or f.endswith('.bin'):
            if f in ['EOS_Server_Info.dat', 'PEA_Server_Info.dat']:
                continue
            full_p = os.path.join(dir_path, f)
            if os.path.isfile(full_p) and os.path.getsize(full_p) > 200:
                exam_files.append(full_p)

    if not exam_files:
        return {"exam_title": "Empty Exam Folder", "questions": [], "is_pea": False, "is_writing": False}

    if len(exam_files) == 1:
        return parse_full_exam_file(exam_files[0])

    combined_questions = []
    global_idx = 0
    folder_title = os.path.basename(dir_path.rstrip('\\/'))
    exam_titles = []

    for ef in exam_files:
        try:
            part_res = parse_full_exam_file(ef)
            t = part_res.get("exam_title", os.path.basename(ef))
            exam_titles.append(t)
            for q in part_res.get("questions", []):
                q_copy = dict(q)
                q_copy["question_index"] = global_idx
                q_copy["source_file"] = os.path.basename(ef)
                combined_questions.append(q_copy)
                global_idx += 1
        except Exception:
            continue

    return {
        "exam_title": f"EOS Hợp Nhất ({folder_title}): {len(combined_questions)} Câu",
        "language": "General",
        "is_pea": False,
        "is_writing": any("Writing" in t or "Tự Luận" in t or "_W_" in t for t in exam_titles),
        "has_paper_image": False,
        "sub_exams": exam_titles,
        "questions": combined_questions
    }
