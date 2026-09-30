import os
import sys
import json
import sqlite3

# Thêm thư mục web portal vào sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database

def run_tests():
    print("=== BẮT ĐẦU TEST TOÀN DIỆN CƠ CHẾ ĐỒNG BỘ & CHỐNG DỒN ĐỀ THI ===")
    test_hwid = "TEST-STUDENT-AUTO-RESET-HWID-001"
    
    # Dọn dẹp DB trước khi test
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM live_exam_questions WHERE hwid = ?", (test_hwid,))
    c.execute("DELETE FROM live_exam_sessions WHERE hwid = ?", (test_hwid,))
    conn.commit()
    conn.close()

    # 1. Giả lập Thí sinh nạp Đề 1 (30 câu)
    print("\n[Bước 1] Thí sinh mở Đề 1: 'Kỳ thi Lập trình Java 1' (30 câu hỏi)")
    exam1_questions = []
    for i in range(30):
        exam1_questions.append({
            "question_index": i,
            "question_text": f"Câu hỏi số {i+1} môn Java: Lệnh nào dùng để khai báo class?",
            "question_type": "radio",
            "options": [{"label": "A", "text": "class", "image_base64": ""}, {"label": "B", "text": "struct", "image_base64": ""}],
            "image_base64": "",
            "current_answer": ""
        })

    ans1, reset1 = database.sync_student_exam_data(
        hwid=test_hwid,
        student_name="Nguyen Van Test",
        exam_title="Kỳ thi Lập trình Java 1",
        questions=exam1_questions,
        page_url="https://exam.fpt.edu.vn/mod/quiz/attempt.php?attempt=10001&page=0",
        return_details=True
    )
    
    q_in_db1 = database.get_live_exam_questions(test_hwid)
    session1 = database.get_live_exam_session(test_hwid)
    print(f"-> Số câu hỏi Đề 1 lưu trong DB: {len(q_in_db1)} (Kỳ vọng: 30)")
    print(f"-> Session total_questions: {session1['total_questions']} (Kỳ vọng: 30)")
    assert len(q_in_db1) == 30, f"Lỗi: Số câu hỏi không phải 30 mà là {len(q_in_db1)}"
    assert session1['total_questions'] == 30

    # Support chọn đáp án cho câu 5 của Đề 1
    database.set_question_support_answer(test_hwid, 5, "0")
    q5_check = [q for q in database.get_live_exam_questions(test_hwid) if q["question_index"] == 5][0]
    print(f"-> Support đã chọn đáp án cho câu 5 Đề 1: {q5_check['support_answer']}")
    assert q5_check['support_answer'] == "0"

    # 2. Giả lập tiếp tục trang 2 của ĐỀ 1 (Cùng đề, không được reset!)
    print("\n[Bước 2] Thí sinh chuyển sang trang 2 của CÙNG Đề 1 (attempt=10001&page=1)")
    ans1_p2, reset1_p2 = database.sync_student_exam_data(
        hwid=test_hwid,
        student_name="Nguyen Van Test",
        exam_title="Kỳ thi Lập trình Java 1",
        questions=exam1_questions[15:], # gửi tiếp 15 câu sau
        page_url="https://exam.fpt.edu.vn/mod/quiz/attempt.php?attempt=10001&page=1",
        return_details=True
    )
    print(f"-> should_reset_cache khi cùng đề: {reset1_p2} (Kỳ vọng: False)")
    assert reset1_p2 is False, "Lỗi: Cùng một đề thi không được reset cache!"
    q_in_db1_p2 = database.get_live_exam_questions(test_hwid)
    print(f"-> Số câu hỏi sau khi sang trang 2: {len(q_in_db1_p2)} (Kỳ vọng: 30)")
    assert len(q_in_db1_p2) == 30

    # 3. Thí sinh hoàn thành bài thi Java và chuyển sang ĐỀ 2 (15 câu)
    print("\n[Bước 3] Thí sinh chuyển sang Đề 2: 'Kỳ thi Tiếng Anh Chuyên Ngành' (15 câu, attempt=20002)")
    exam2_questions = []
    for i in range(15):
        exam2_questions.append({
            "question_index": i,
            "question_text": f"Question {i+1} English: Choose the correct preposition for this context.",
            "question_type": "radio",
            "options": [{"label": "A", "text": "in", "image_base64": ""}, {"label": "B", "text": "on", "image_base64": ""}],
            "image_base64": "",
            "current_answer": ""
        })

    ans2, reset2 = database.sync_student_exam_data(
        hwid=test_hwid,
        student_name="Nguyen Van Test",
        exam_title="Kỳ thi Tiếng Anh Chuyên Ngành",
        questions=exam2_questions,
        page_url="https://exam.fpt.edu.vn/mod/quiz/attempt.php?attempt=20002&page=0",
        return_details=True
    )
    
    print(f"-> should_reset_cache khi sang Đề 2: {reset2} (Kỳ vọng: True)")
    assert reset2 is True, "Lỗi: Khi sang đề mới, hệ thống PHẢI trả về should_reset_cache = True!"

    q_in_db2 = database.get_live_exam_questions(test_hwid)
    session2 = database.get_live_exam_session(test_hwid)
    print(f"-> Số câu hỏi Đề 2 lưu trong DB: {len(q_in_db2)} (Kỳ vọng: ĐÚNG 15 CÂU, KHÔNG ĐƯỢC 30 HAY 45 CÂU!)")
    print(f"-> Session total_questions: {session2['total_questions']} (Kỳ vọng: 15)")
    print(f"-> Tên bài thi trong session: {session2['exam_title']}")
    
    assert len(q_in_db2) == 15, f"LỖI DỒN ĐỀ: DB có {len(q_in_db2)} câu thay vì 15 câu của Đề 2!"
    assert session2['total_questions'] == 15
    assert "Tiếng Anh" in session2['exam_title']
    
    # Kiểm tra nội dung câu hỏi đầu tiên: Phải là câu hỏi tiếng Anh, không phải câu hỏi Java cũ
    print(f"-> Nội dung Câu 1 hiện tại: '{q_in_db2[0]['question_text']}'")
    assert "English" in q_in_db2[0]['question_text'], "Lỗi: Câu 1 không phải của Đề 2!"

    # Kiểm tra xem Đề 1 đã được tự động đóng gói file ZIP chưa
    archives = database.list_archived_exam_sources()
    matching_archives = [a for a in archives if a["hwid"] == test_hwid]
    print(f"-> Đã tìm thấy {len(matching_archives)} bản sao lưu ZIP của Đề 1 trong kho lưu trữ:")
    for a in matching_archives:
        print(f"   + File: {a['archive_filename']} | Môn: {a['exam_title']} | Tổng số câu: {a['total_questions']}")
    assert len(matching_archives) >= 1, "Lỗi: Chưa tự động archive đề cũ thành file ZIP!"

    # 4. Thử nghiệm nút Bắt Đầu Đề Mới (Manual Reset) của Admin / Support
    print("\n[Bước 4] Admin / Support bấm nút 'Bắt Đầu Đề Mới (Reset ca thi)'")
    reset_res = database.reset_and_archive_exam_session(test_hwid)
    print(f"-> Kết quả reset: {reset_res['message']}")
    
    session_reset = database.get_live_exam_session(test_hwid)
    q_reset = database.get_live_exam_questions(test_hwid)
    print(f"-> Số câu hỏi trong DB sau khi bấm Reset: {len(q_reset)} (Kỳ vọng: 0)")
    print(f"-> Trạng thái session: {session_reset['status']} (Kỳ vọng: reset_requested)")
    assert len(q_reset) == 0
    assert session_reset['status'] == "reset_requested"

    # Giả lập client SEB ping sync-answers: Phải nhận được cờ should_reset_cache = True
    session_check = database.get_live_exam_session(test_hwid)
    assert session_check["status"] == "reset_requested"
    database.update_live_exam_session_status(test_hwid, "active")
    print("-> Client nhận cờ should_reset_cache = True và tự động xóa sạch sessionStorage.")

    # Dọn dẹp dữ liệu test
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM live_exam_questions WHERE hwid = ?", (test_hwid,))
    c.execute("DELETE FROM live_exam_sessions WHERE hwid = ?", (test_hwid,))
    c.execute("DELETE FROM archived_exam_sources WHERE hwid = ?", (test_hwid,))
    conn.commit()
    conn.close()

    print("\n🎉 TẤT CẢ CÁC BƯỚC TEST ĐÃ THÀNH CÔNG 100%! HỆ THỐNG ĐÃ SẴN SÀNG HOẠT ĐỘNG HOÀN HẢO!")

if __name__ == "__main__":
    run_tests()
