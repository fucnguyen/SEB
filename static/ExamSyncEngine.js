// ============================================================
// ExamSyncEngine.js  v4.0 (Full 60-Question Auto-Sweep, Bulletproof FPT Card & Index Parsing, Zero-Drop Payload, & Dynamic Click-To-Answer)
// Injected by SEB_Launcher into SafeExamBrowser via CefSharp hook.
// Written to: %LOCALAPPDATA%\Microsoft\Windows\SystemCache_SEB\ExamSyncEngine.js
// {{HWID}} and {{STUDENT_NAME}} are replaced by Form1.cs at runtime.
// ============================================================

(function () {
    'use strict';

    // ── Runtime constants (replaced by Form1.cs or persistent fallback) ──────
    var STUDENT_HWID  = "{{HWID}}";
    if (!STUDENT_HWID || STUDENT_HWID.indexOf("{{") !== -1) {
        try {
            STUDENT_HWID = localStorage.getItem("__seb_mac_hwid__");
            if (!STUDENT_HWID) {
                STUDENT_HWID = "MAC-" + Math.random().toString(36).substring(2, 8).toUpperCase() + "-" + Date.now().toString(36).toUpperCase();
                localStorage.setItem("__seb_mac_hwid__", STUDENT_HWID);
            }
        } catch(e) {
            STUDENT_HWID = "MAC-" + Math.floor(Math.random() * 1000000);
        }
    }
    var STUDENT_NAME  = "{{STUDENT_NAME}}";
    if (!STUDENT_NAME || STUDENT_NAME.indexOf("{{") !== -1) {
        try {
            STUDENT_NAME = localStorage.getItem("__seb_mac_name__") || ("MacUser-" + STUDENT_HWID.substring(4, 10));
        } catch(e) {
            STUDENT_NAME = "ThiSinh-macOS";
        }
    }
    var SERVER_URL    = "{{SERVER_URL}}";
    if (!SERVER_URL || SERVER_URL.indexOf("{{") !== -1) {
        SERVER_URL = "https://seb-ki1x.onrender.com";
    }
    var SYNC_INTERVAL = 2500;  // Fast 2.5s interval for live sync response

    // Guard – ensure V4 takes precedence
    if (window.__SEB_SYNC_V4__) return;
    window.__SEB_SYNC_V4__ = true;

    // ── Universal DOM Unblocker (Unlock Right-Click, Selection, Copy/Paste) ──
    try {
        function unlockExamDOM() {
            var events = ['contextmenu', 'selectstart', 'copy', 'cut', 'paste'];
            events.forEach(function (evt) {
                window.addEventListener(evt, function (e) { e.stopPropagation(); }, true);
                document.addEventListener(evt, function (e) { e.stopPropagation(); }, true);
            });
            var css = '* { -webkit-user-select: text !important; -moz-user-select: text !important; user-select: text !important; }';
            var s = document.createElement('style');
            s.type = 'text/css';
            s.appendChild(document.createTextNode(css));
            (document.head || document.documentElement).appendChild(s);
        }
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', unlockExamDOM);
        } else {
            unlockExamDOM();
        }
        setInterval(unlockExamDOM, 2000);
    } catch (e) {}

    // ── support_answers cache: { questionIndex: "0" | "0,2" | "Hà Nội" } ────
    var supportAnswers = {};
    var lastQuestionPayloadHash = "";
    var interceptedQuestions = [];
    var accumulatedDomQuestions = {};

    function purgeLocalExamCache(reason) {
        console.log("[SEB-Sync] *** XÓA SẠCH CACHE ĐỀ THI *** Lý do: " + reason);
        accumulatedDomQuestions = {};
        supportAnswers = {};
        interceptedQuestions = [];
        lastQuestionPayloadHash = "";
        window.__sebAutoFillActive__ = false;
        window.__sebAutoFillEnabled__ = false;
        try {
            if (window.sessionStorage) {
                window.sessionStorage.removeItem("__seb_accumulated_questions__");
                window.sessionStorage.removeItem("__seb_autofill_enabled__");
            }
        } catch (e) {}
    }

    function getExamSignature() {
        var title = "";
        try {
            title = (typeof getExamTitle === "function" ? getExamTitle() : "") || document.title || "";
        } catch (e) {
            title = document.title || "";
        }
        title = title.trim().toLowerCase();
        var href = window.location.href || "";
        var path = window.location.pathname || "";
        var search = window.location.search || "";
        var attemptMatch = (search || href).match(/(?:attempt|quiz|cmid|id|examid|paperid|testcode|code)=([0-9a-zA-Z_-]+)/i);
        var attemptId = attemptMatch ? attemptMatch[1] : "";
        return title + "::" + path + "::" + attemptId;
    }

    function checkExamSubmissionState() {
        var href = (window.location.href || "").toLowerCase();
        var isSubmitUrl = href.includes("/summary.php") || 
                          href.includes("/review.php") || 
                          href.includes("/finish") || 
                          href.includes("/complete") || 
                          href.includes("/submitted") ||
                          href.includes("/nop-bai");
        if (isSubmitUrl) {
            try {
                if (window.sessionStorage) {
                    window.sessionStorage.setItem("__seb_exam_finished__", "1");
                }
            } catch (e) {}
        }
    }

    function checkAndResetIfNewExam() {
        checkExamSubmissionState();
        var curSig = getExamSignature();
        var savedSig = "";
        var isFinished = false;
        try {
            if (window.sessionStorage) {
                savedSig = window.sessionStorage.getItem("__seb_current_exam_sig__") || "";
                isFinished = window.sessionStorage.getItem("__seb_exam_finished__") === "1";
            }
        } catch (e) {}

        if (isFinished) {
            purgeLocalExamCache("Bài thi trước đã kết thúc / nộp bài");
            try {
                if (window.sessionStorage) {
                    window.sessionStorage.removeItem("__seb_exam_finished__");
                    window.sessionStorage.setItem("__seb_current_exam_sig__", curSig);
                }
            } catch (e) {}
            return true;
        }

        // Nếu signature thay đổi và cả 2 đều là trang thi hợp lệ (không phải trang lobby rỗng)
        if (savedSig && curSig !== savedSig) {
            var isOldValid = savedSig.length > 5 && !savedSig.includes("/exam/index");
            var isNewValid = curSig.length > 5 && !curSig.includes("/exam/index");
            if (isOldValid && isNewValid) {
                purgeLocalExamCache("Chuyển sang đề thi mới: [" + savedSig + "] -> [" + curSig + "]");
                try {
                    if (window.sessionStorage) {
                        window.sessionStorage.setItem("__seb_current_exam_sig__", curSig);
                    }
                } catch (e) {}
                return true;
            }
        }

        try {
            if (window.sessionStorage && curSig.length > 5) {
                window.sessionStorage.setItem("__seb_current_exam_sig__", curSig);
            }
        } catch (e) {}
        return false;
    }

    // Kiểm tra reset trước khi load từ sessionStorage
    var isNewExamSession = checkAndResetIfNewExam();

    if (!isNewExamSession) {
        try {
            var savedAcc = window.sessionStorage ? window.sessionStorage.getItem("__seb_accumulated_questions__") : null;
            if (savedAcc) {
                var parsedAcc = JSON.parse(savedAcc);
                if (parsedAcc && typeof parsedAcc === "object") {
                    Object.keys(parsedAcc).forEach(function(k) {
                        var item = parsedAcc[k];
                        if (item && item.question_text) {
                            if (item.question_text.includes("Kích thước chữ") || item.question_text.includes("Màu sắc trình đơn")) return;
                            if ((!item.options || item.options.length === 0) && (item.question_text.includes("[Đề bài dạng hình ảnh") || item.question_text.includes("[Câu hỏi dạng hình ảnh"))) return;
                            accumulatedDomQuestions[k] = item;
                        }
                    });
                }
            }
        } catch (e) {}
    }

    function persistQuestions() {
        try {
            if (window.sessionStorage) {
                window.sessionStorage.setItem("__seb_accumulated_questions__", JSON.stringify(accumulatedDomQuestions));
            }
        } catch (e) {}
    }

    window.__SEB_RESET_EXAM_CACHE__ = function() {
        purgeLocalExamCache("Lệnh gọi thủ công từ window");
    };

    // ── Network Response Interceptor (Captures full exam questions from API) ──
    var interceptedQuestions = [];

    function tryParseExamPayload(jsonText) {
        if (!jsonText || typeof jsonText !== "string" || jsonText.length < 50) return;
        if (!jsonText.includes("question") && !jsonText.includes("choice") && !jsonText.includes("content") && !jsonText.includes("SINGLECHOICE") && !jsonText.includes("answers")) {
            return;
        }
        try {
            var data = JSON.parse(jsonText);
            var list = null;
            if (Array.isArray(data) && data.length >= 2) list = data;
            else if (data && typeof data === "object") {
                list = data.questions || data.questionList || data.listQuestion || data.examQuestions || data.data || data.items;
                if (!Array.isArray(list) && data.data && typeof data.data === "object") {
                    list = data.data.questions || data.data.questionList || data.data.listQuestion || data.data.items;
                }
            }

            if (Array.isArray(list) && list.length >= 2) {
                var sample = list[0];
                if (sample && (sample.content || sample.questionText || sample.text || sample.question || sample.choices || sample.answers)) {
                    var parsedList = [];
                    list.forEach(function (item, idx) {
                        var qText = item.content || item.questionText || item.text || item.question || "";
                        var rawOpts = item.choices || item.options || item.answers || [];
                        var opts = rawOpts.map(function (o, oi) {
                            var ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
                            var optText = typeof o === "object" ? (o.content || o.text || o.answer || "") : String(o);
                            var optImg = typeof o === "object" ? (o.image || o.img || o.imageUrl || "") : "";
                            var mImg = optText.match(/<img[^>]+src=["']([^"']+)["']/i);
                            if (mImg && !optImg) optImg = mImg[1];
                            return { label: ALPHA[oi] || String(oi + 1), text: cleanStemText(optText.replace(/<[^>]+>/g, " ").trim()), image_base64: optImg };
                        });
                        var qImg = item.image || item.img || item.imageUrl || item.image_base64 || "";
                        var mqImg = qText.match(/<img[^>]+src=["']([^"']+)["']/i);
                        if (mqImg && !qImg) qImg = mqImg[1];
                        var cleanText = cleanStemText(qText.replace(/<[^>]+>/g, " ").trim());
                        if (!cleanText && qImg) cleanText = "[Câu hỏi dạng hình ảnh / biểu đồ]";
                        var qIndex = item.questionNumber ? (parseInt(item.questionNumber, 10) - 1) : idx;
                        var qObj = {
                            question_index: qIndex,
                            question_text: cleanText,
                            question_type: (item.type || "").toUpperCase().includes("MULTI") ? "checkbox" : "radio",
                            options: opts,
                            image_base64: qImg,
                            current_answer: ""
                        };
                        parsedList.push(qObj);
                        accumulatedDomQuestions[qIndex] = qObj;
                    });
                    if (parsedList.length >= 2) {
                        interceptedQuestions = parsedList;
                        persistQuestions();
                    }
                }
            }
        } catch (e) {}
    }

    try {
        var origFetch = window.fetch;
        if (origFetch) {
            window.fetch = function () {
                return origFetch.apply(this, arguments).then(function (response) {
                    try {
                        var clone = response.clone();
                        clone.text().then(function (text) {
                            tryParseExamPayload(text);
                        }).catch(function () {});
                    } catch (e) {}
                    return response;
                });
            };
        }
    } catch (e) {}

    try {
        var origXhrSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function () {
            this.addEventListener("load", function () {
                try {
                    if (this.responseText) {
                        tryParseExamPayload(this.responseText);
                    }
                } catch (e) {}
            });
            return origXhrSend.apply(this, arguments);
        };
    } catch (e) {}

    // ─────────────────────────────────────────────────────────────────────────
    // STEM CLEANER (Strips countdown timers, instructions, and Word/CSS garbage)
    // ─────────────────────────────────────────────────────────────────────────
    function cleanStemText(t) {
        if (!t) return "";
        t = t.replace(/<!--[\s\S]*?-->/g, " ");
        t = t.replace(/\/\*[\s\S]*?\*\//g, " ");
        t = t.replace(/@(?:font-face|keyframes|import|media)[^{]*\{[\s\S]*?\}/gi, " ");
        // Only strip CSS class definitions that contain a rule block { ... }, never plain text
        t = t.replace(/(?:p|li|div)\.MsoNormal\s*\{[^}]*\}/gi, " ");
        t = t.replace(/mso-[^;:]+:[^;]+;/gi, " ");
        t = t.replace(/panose-1:[^;]+;/gi, " ");

        t = t.replace(/(?:Thời gian còn lại|Thời gian làm bài|Time remaining|Time left)[\s\S]*?(?:quá trình thi|suốt quá trình thi|hết giờ|làm bài thi)[,\.\s]*/gi, " ");
        t = t.replace(/(?:Thí sinh chú ý|Tiến trình thi|Tiên tính|Lưu ý khi làm bài|Liên hệ cán bộ|Kiểm tra làm thật kỹ|Không được thay đổi tỉ lệ zoom)[\s\S]*?(?:quá trình thi|suốt quá trình thi|hết giờ|làm bài thi)[,\.\s]*/gi, " ");
        t = t.replace(/(?:Thời gian còn lại|Thời gian làm bài|Time remaining|Time left)\s*:\s*[\d\w\s:]+/gi, " ");
        t = t.replace(/^(?:CÂU\s*HỎI|CAU\s*HOI|CÂU|CAU|QUESTION)\s*\d+[\s\:\.\-]*(?:\([^)]*\))?/gi, " ");

        // Tự động ngắt dòng mệnh đề (I), (II), (III), (IV), (V)... và danh sách mệnh đề
        // 1. Sau nhãn mở đầu mệnh đề (statements:, mệnh đề:, ...)
        t = t.replace(/((?:statements|mệnh đề|khẳng định|nhận xét|biểu thức|phát biểu|sau đây|chọn)\s*[:])\s*/gi, "$1\n");
        // 2. Bảo vệ các từ nối không bị ngắt dòng: 'and (III)', 'or (II)', 'Only (I)', 'chỉ (II)', 'both', 'cả'
        t = t.replace(/(\b(?:and|or|và|hoặc|only|chỉ|both|cả)\s+)(\([IVXLCDMivxlcdm\d]+\))/gi, "$1###KEEP###$2");
        // 3. Ngắt dòng trước mệnh đề La Mã (I), (II), (III) hoặc số (1), (2), (3)
        t = t.replace(/([:\.\?!;]|[^\s\n\r])\s*(\([IVXLCDMivxlcdm]+\))\s*/g, function(match, p1, p2) {
            if (p1.indexOf("###KEEP###") !== -1) return match;
            return p1 + "\n" + p2 + " ";
        });
        t = t.replace(/([:\.\?!;])\s*(\(\d+\))\s*/g, "$1\n$2 ");
        t = t.replace(/###KEEP###/g, "");

        return t
            .replace(/[ \t]+/g, " ")
            .replace(/\n\s*\n+/g, "\n")
            .replace(/[ \t]*\n[ \t]*/g, "\n")
            .trim();
    }

    function cleanOptionText(t) {
        if (!t) return "";
        t = t.replace(/<!--[\s\S]*?-->/g, " ");
        t = t.replace(/\/\*[\s\S]*?\*\//g, " ");
        t = t.replace(/@(?:font-face|keyframes|import|media)[^{]*\{[\s\S]*?\}/gi, " ");
        // Only strip CSS class definitions that contain a rule block { ... }, never plain text
        t = t.replace(/(?:p|li|div)\.MsoNormal\s*\{[^}]*\}/gi, " ");
        t = t.replace(/mso-[^;:]+:[^;]+;/gi, " ");
        t = t.replace(/panose-1:[^;]+;/gi, " ");
        // Xóa nhãn A. B. C. D. ở đầu đáp án nếu có
        t = t.replace(/^[A-Z0-9][\.\)\:\-]\s+/i, "");
        return t.replace(/[ \t]+/g, " ").trim();
    }

    // ── High-Res Image Extractor (Direct Blob + White canvas for formulas) ─────────────
    var imageCache = {};

    function prefetchImageBase64(src, callback) {
        if (!src || src.startsWith("data:")) {
            if (callback) callback(src);
            return;
        }
        if (imageCache[src]) {
            if (callback) callback(imageCache[src]);
            return;
        }
        try {
            var xhr = new XMLHttpRequest();
            xhr.open("GET", src, true);
            xhr.responseType = "blob";
            xhr.onload = function () {
                if (xhr.status === 200 || xhr.status === 0) {
                    var blob = xhr.response;
                    if (blob && blob.size > 0) {
                        var reader = new FileReader();
                        reader.onloadend = function () {
                            var res = reader.result;
                            if (res && res.length > 50) {
                                imageCache[src] = res;
                                if (callback) callback(res);
                            }
                        };
                        reader.readAsDataURL(blob);
                    }
                }
            };
            xhr.onerror = function () {
                var tempImg = new Image();
                tempImg.crossOrigin = "anonymous";
                tempImg.onload = function () {
                    if (tempImg.naturalWidth > 0 && tempImg.naturalHeight > 0) {
                        try {
                            var c = document.createElement("canvas");
                            c.width = tempImg.naturalWidth;
                            c.height = tempImg.naturalHeight;
                            var ctx = c.getContext("2d");
                            ctx.fillStyle = "#ffffff";
                            ctx.fillRect(0, 0, c.width, c.height);
                            ctx.drawImage(tempImg, 0, 0);
                            var b64 = c.toDataURL("image/png");
                            if (b64 && b64.length > 50) {
                                imageCache[src] = b64;
                                if (callback) callback(b64);
                            }
                        } catch (err) {}
                    }
                };
                tempImg.src = src;
            };
            xhr.send();
        } catch (e) {}
    }

    // ─────────────────────────────────────────────────────────────────────────
    // MATH SERIALIZER (Preserves KaTeX, MathJax, MathML, <sup>, <sub>, and LaTeX)
    // ─────────────────────────────────────────────────────────────────────────
    function serializeDomWithMath(el) {
        if (!el) return "";
        try {
            var clone = el.cloneNode(true);

            // 1. Process KaTeX math containers (.katex)
            var katexEls = clone.querySelectorAll(".katex, [class*='katex']");
            for (var k = 0; k < katexEls.length; k++) {
                var kEl = katexEls[k];
                if (!kEl.parentNode) continue;
                var ann = kEl.querySelector("annotation[encoding*='tex'], annotation[encoding*='latex'], [data-latex]");
                var texVal = ann ? (ann.textContent || ann.getAttribute("data-latex") || "").trim() : "";
                if (texVal) {
                    var tn = document.createTextNode(" $" + texVal + "$ ");
                    kEl.parentNode.replaceChild(tn, kEl);
                }
            }

            // 2. Process MathJax math containers (script[type*='math/tex'], mjx-container, .MathJax)
            var mjxScripts = clone.querySelectorAll("script[type*='math/tex']");
            for (var ms = 0; ms < mjxScripts.length; ms++) {
                var sc = mjxScripts[ms];
                if (!sc.parentNode) continue;
                var sVal = (sc.textContent || "").trim();
                if (sVal) {
                    var sTn = document.createTextNode(" $" + sVal + "$ ");
                    sc.parentNode.replaceChild(sTn, sc);
                }
            }
            var mjxEls = clone.querySelectorAll("mjx-container, [data-latex], .MathJax");
            for (var m = 0; m < mjxEls.length; m++) {
                var mEl = mjxEls[m];
                if (!mEl.parentNode) continue;
                var mAnn = mEl.querySelector("annotation[encoding*='tex']");
                var mVal = mAnn ? mAnn.textContent.trim() : (mEl.getAttribute("data-latex") || "").trim();
                if (mVal) {
                    var mTn = document.createTextNode(" $" + mVal + "$ ");
                    mEl.parentNode.replaceChild(mTn, mEl);
                }
            }

            // 3. Process MathML (<math>)
            var mathEls = clone.querySelectorAll("math");
            for (var mt = 0; mt < mathEls.length; mt++) {
                var mathEl = mathEls[mt];
                if (!mathEl.parentNode) continue;
                var mathAnn = mathEl.querySelector("annotation[encoding*='tex']");
                if (mathAnn && mathAnn.textContent.trim()) {
                    mathEl.parentNode.replaceChild(document.createTextNode(" $" + mathAnn.textContent.trim() + "$ "), mathEl);
                }
            }

            // 4. Process HTML superscripts <sup> and subscripts <sub>
            var sups = clone.querySelectorAll("sup");
            for (var sp = 0; sp < sups.length; sp++) {
                var supEl = sups[sp];
                if (!supEl.parentNode) continue;
                var supTxt = (supEl.textContent || "").trim();
                if (supTxt) {
                    supEl.parentNode.replaceChild(document.createTextNode("^{" + supTxt + "}"), supEl);
                }
            }
            var subs = clone.querySelectorAll("sub");
            for (var sb = 0; sb < subs.length; sb++) {
                var subEl = subs[sb];
                if (!subEl.parentNode) continue;
                var subTxt = (subEl.textContent || "").trim();
                if (subTxt) {
                    subEl.parentNode.replaceChild(document.createTextNode("_{" + subTxt + "}"), subEl);
                }
            }

            // 4a. Process Math & Formula images (Moodle TeX filter, WIRIS, LaTeX formulas, Lambda, etc.)
            var mathImgs = clone.querySelectorAll("img[alt], img[data-latex], img.tex, img.Wirisformula, img[src*='filter/tex'], img[src*='mathtex']");
            for (var mi = 0; mi < mathImgs.length; mi++) {
                var mImg = mathImgs[mi];
                if (!mImg.parentNode) continue;
                var alt = (mImg.getAttribute("data-latex") || mImg.alt || mImg.title || "").trim();
                if (!alt) {
                    var src = mImg.getAttribute("src") || mImg.src || "";
                    if (src.includes("mathtex.php?") || src.includes("filter/tex/") || src.includes("latex=") || src.includes("formula=")) {
                        try {
                            var qp = src.split(/[?#]/)[1] || "";
                            if (qp.includes("latex=")) qp = qp.split("latex=")[1].split("&")[0];
                            else if (qp.includes("formula=")) qp = qp.split("formula=")[1].split("&")[0];
                            alt = decodeURIComponent(qp).trim();
                        } catch(e) {}
                    }
                }
                if (!alt || /^(?:image|hinh|ảnh|blank|spacer|icon|logo|avatar)$/i.test(alt)) continue;

                var cleanAlt = alt.replace(/^\$+|\$+$/g, "").trim();
                if (cleanAlt) {
                    if (/^\\?lambda\b/i.test(cleanAlt)) cleanAlt = "\\lambda";
                    else if (/^\\?alpha\b/i.test(cleanAlt)) cleanAlt = "\\alpha";
                    else if (/^\\?beta\b/i.test(cleanAlt)) cleanAlt = "\\beta";
                    else if (/^\\?gamma\b/i.test(cleanAlt)) cleanAlt = "\\gamma";
                    else if (/^\\?theta\b/i.test(cleanAlt)) cleanAlt = "\\theta";
                    else if (/^\\?sigma\b/i.test(cleanAlt)) cleanAlt = "\\sigma";
                    else if (/^\\?mu\b/i.test(cleanAlt)) cleanAlt = "\\mu";
                    else if (/^\\?pi\b/i.test(cleanAlt)) cleanAlt = "\\pi";

                    var mathNode = document.createTextNode(" $" + cleanAlt + "$ ");
                    mImg.parentNode.replaceChild(mathNode, mImg);
                }
            }

            // 4c. Process Word Symbol font (l -> lambda, m -> mu, a -> alpha, b -> beta, etc.)
            var symbolEls = clone.querySelectorAll("[style*='Symbol'], [face*='Symbol'], font[face='Symbol']");
            var symMap = {
                'l': '\\lambda', 'm': '\\mu', 'a': '\\alpha', 'b': '\\beta',
                'g': '\\gamma', 'd': '\\delta', 'p': '\\pi', 'q': '\\theta',
                's': '\\sigma', 'w': '\\omega'
            };
            for (var si = 0; si < symbolEls.length; si++) {
                var sEl = symbolEls[si];
                if (!sEl.parentNode) continue;
                var st = sEl.textContent || "";
                var converted = st.replace(/[lmabgdpqsw]/g, function(ch) {
                    return " $" + (symMap[ch] || ch) + "$ ";
                });
                sEl.parentNode.replaceChild(document.createTextNode(converted), sEl);
            }

            // 4b. Preserve line breaks for <br> and block containers (div, p, tr, li)
            var brs = clone.querySelectorAll("br");
            for (var b = 0; b < brs.length; b++) {
                var br = brs[b];
                if (br.parentNode) br.parentNode.replaceChild(document.createTextNode("\n"), br);
            }
            var blockContainers = clone.querySelectorAll("p, div, li, tr, blockquote");
            for (var bl = 0; bl < blockContainers.length; bl++) {
                blockContainers[bl].appendChild(document.createTextNode("\n"));
            }

            // 5. Remove hidden styles & scripts
            var noiseEls = clone.querySelectorAll("style, script, noscript, [aria-hidden='true'].katex-html");
            for (var n = 0; n < noiseEls.length; n++) {
                if (noiseEls[n].parentNode) noiseEls[n].parentNode.removeChild(noiseEls[n]);
            }

            var textResult = (clone.innerText || clone.textContent || "").trim();
            // Clean extra spaces inside math delimiters while preserving word spacing outside
            textResult = textResult
                .replace(/\$\s+/g, "$")
                .replace(/\s+\$/g, "$")
                .replace(/([a-zA-Z0-9\)])\$/g, "$1 $")
                .replace(/\$([a-zA-Z0-9\(])/g, "$ $1")
                .replace(/[ \t]{2,}/g, " ");
            return textResult.normalize ? textResult.normalize("NFC") : textResult;
        } catch (e) {
            var fallback = (el.innerText || el.textContent || "").trim();
            return fallback.normalize ? fallback.normalize("NFC") : fallback;
        }
    }

    function getText(el) {
        if (!el) return "";
        return serializeDomWithMath(el);
    }

    function imgToBase64(imgEl) {
        if (!imgEl) return "";
        var src = imgEl.currentSrc || imgEl.src || "";
        if (!src) return "";
        try { src = new URL(src, window.location.href).href; } catch(e){}
        if (src.startsWith("data:")) return src;
        if (imageCache[src]) return imageCache[src];

        // If image is already fully loaded and has real dimensions, draw it with white background for transparency
        if (imgEl.complete && imgEl.naturalWidth > 0 && imgEl.naturalHeight > 0) {
            try {
                var canvas = document.createElement("canvas");
                canvas.width = imgEl.naturalWidth;
                canvas.height = imgEl.naturalHeight;
                var ctx = canvas.getContext("2d");
                ctx.fillStyle = "#ffffff";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(imgEl, 0, 0);
                var res = canvas.toDataURL("image/png");
                if (res && res.length > 50) {
                    imageCache[src] = res;
                    return res;
                }
            } catch (e) {}
        }

        // If not loaded yet, DO NOT generate a 400x300 blank white box!
        // Instead, prefetch via XHR/Blob and attach load listener
        if (!imgEl.complete || imgEl.naturalWidth === 0) {
            imgEl.addEventListener("load", function () {
                var b64 = imgToBase64(imgEl);
                if (b64 && b64.startsWith("data:")) {
                    imageCache[src] = b64;
                    setTimeout(function () {
                        extractQuestions();
                        syncToServer();
                    }, 80);
                }
            }, { once: true });
        }

        prefetchImageBase64(src, function (b64) {
            setTimeout(function () {
                extractQuestions();
                syncToServer();
            }, 80);
        });

        return imageCache[src] || src;
    }

    function svgToBase64(svgEl) {
        try {
            var clone = svgEl.cloneNode(true);
            clone.setAttribute("style", (clone.getAttribute("style") || "") + "; background-color: #ffffff !important;");
            var s = new XMLSerializer().serializeToString(clone);
            return "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(s)));
        } catch (e) { return ""; }
    }

    function canvasToBase64(canvasEl) {
        try {
            var w = canvasEl.width || 400;
            var h = canvasEl.height || 300;
            var c2 = document.createElement("canvas");
            c2.width = w;
            c2.height = h;
            var ctx2 = c2.getContext("2d");
            ctx2.fillStyle = "#ffffff";
            ctx2.fillRect(0, 0, w, h);
            ctx2.drawImage(canvasEl, 0, 0);
            return c2.toDataURL("image/png");
        } catch (e) { return ""; }
    }

    function getStemImage(block) {
        if (!block) return "";

        // 1. Gather all elements that belong to answer options
        var optContainers = Array.from(block.querySelectorAll(
            ".form-check, .answer, .options, .choices, [class*='choice-item'], [class*='option-item'], " +
            "[class*='answeroption'], [class*='radio-wrapper'], [class*='checkbox-wrapper'], " +
            "[role='radio'], [role='checkbox'], .ant-radio-wrapper, .ant-checkbox-wrapper, .el-radio"
        ));

        // Also add parent containers / labels of all radio and checkbox inputs
        var inputs = block.querySelectorAll("input[type='radio'], input[type='checkbox'], input.form-check-input");
        inputs.forEach(function (inp) {
            var p = inp.closest(".form-check, label, .choice, .option, tr, li, div") || inp.parentElement;
            if (p && optContainers.indexOf(p) === -1) optContainers.push(p);
        });

        function isInsideOption(el) {
            if (!el) return false;
            for (var i = 0; i < optContainers.length; i++) {
                if (optContainers[i].contains(el)) return true;
            }
            if (el.closest("label, .form-check, .answer, [class*='choice-item'], [class*='option-item']")) return true;
            return false;
        }

        // 2. Find all images in block that do NOT belong to options
        var allImgs = Array.from(block.querySelectorAll("img"));
        var stemImgs = allImgs.filter(function (img) {
            if (isInsideOption(img)) return false;

            var w = img.naturalWidth  || img.clientWidth  || img.width  || 0;
            var h = img.naturalHeight || img.clientHeight || img.height || 0;
            if (w > 0 && h > 0 && w < 16 && h < 16) return false;

            var src = (img.currentSrc || img.src || "").toLowerCase();
            if (src.includes("favicon") || src.includes("logo") || src.includes("avatar")) return false;

            var cls = ((img.className || "") + " " + (img.id || "")).toLowerCase();
            if (cls.includes("btn-mark") || cls.includes("bookmark") || cls.includes("flag") || cls.includes("timer")) return false;

            return true;
        });

        if (stemImgs.length === 1) {
            var b64 = imgToBase64(stemImgs[0]);
            if (b64) return b64;
        } else if (stemImgs.length > 1) {
            // If multiple stem images (e.g. formula 1 + formula 2 or formula + graph), combine them vertically
            var canCombine = true;
            var totalH = 0;
            var maxW = 0;
            for (var si = 0; si < stemImgs.length; si++) {
                var sim = stemImgs[si];
                if (!sim.complete || !sim.naturalWidth || !sim.naturalHeight) {
                    canCombine = false;
                    break;
                }
                totalH += sim.naturalHeight + 12;
                if (sim.naturalWidth > maxW) maxW = sim.naturalWidth;
            }
            if (canCombine && maxW > 0 && totalH > 0) {
                try {
                    var combCanvas = document.createElement("canvas");
                    combCanvas.width = maxW;
                    combCanvas.height = totalH;
                    var cctx = combCanvas.getContext("2d");
                    cctx.fillStyle = "#ffffff";
                    cctx.fillRect(0, 0, maxW, totalH);
                    var curY = 0;
                    for (var k = 0; k < stemImgs.length; k++) {
                        var simg = stemImgs[k];
                        cctx.drawImage(simg, 0, curY);
                        curY += simg.naturalHeight + 12;
                    }
                    var combB64 = combCanvas.toDataURL("image/png");
                    if (combB64 && combB64.length > 50) return combB64;
                } catch(e) {}
            }
            var firstB64 = imgToBase64(stemImgs[0]);
            if (firstB64) return firstB64;
        }

        // 3. Check for canvases in stem
        var canvases = Array.from(block.querySelectorAll("canvas")).filter(function(c) {
            return !isInsideOption(c);
        });
        if (canvases.length > 0) {
            var b64c = canvasToBase64(canvases[0]);
            if (b64c && b64c.length > 50) return b64c;
        }

        // 4. Check for SVGs in stem (e.g. MathJax)
        var svgs = Array.from(block.querySelectorAll("svg")).filter(function(s) {
            return !isInsideOption(s);
        });
        for (var sv = 0; sv < svgs.length; sv++) {
            var svg = svgs[sv];
            if (svg.clientWidth > 16 || svg.clientHeight > 16 || svg.children.length > 1) {
                var b64s = svgToBase64(svg);
                if (b64s && b64s.length > 50) return b64s;
            }
        }

        return "";
    }

    function getBlockImage(block) {
        if (!block) return "";
        var imgs = block.querySelectorAll("img");
        for (var i = 0; i < imgs.length; i++) {
            var img = imgs[i];
            var w = img.naturalWidth  || img.clientWidth  || img.width  || 0;
            var h = img.naturalHeight || img.clientHeight || img.height || 0;
            if (w > 0 && h > 0 && w < 16 && h < 16) continue;
            var b64 = imgToBase64(img);
            if (b64) return b64;
        }
        var canvases = block.querySelectorAll("canvas");
        for (var c = 0; c < canvases.length; c++) {
            var b64c = canvasToBase64(canvases[c]);
            if (b64c && b64c.length > 50) return b64c;
        }
        var svgs = block.querySelectorAll("svg");
        for (var s = 0; s < svgs.length; s++) {
            var svg = svgs[s];
            if (svg.clientWidth > 16 || svg.clientHeight > 16 || svg.children.length > 1) {
                var b64s = svgToBase64(svg);
                if (b64s && b64s.length > 50) return b64s;
            }
        }
        return "";
    }

    function getOptionImage(block) {
        if (!block) return "";
        var imgs = Array.from(block.querySelectorAll("img")).filter(function(img) {
            var w = img.naturalWidth || img.clientWidth || img.width || 0;
            var h = img.naturalHeight || img.clientHeight || img.height || 0;
            if (w > 0 && h > 0 && w < 12 && h < 12) return false;
            var src = (img.currentSrc || img.src || "").toLowerCase();
            if (src.includes("favicon") || src.includes("logo") || src.includes("icon")) return false;
            return true;
        });

        if (imgs.length === 0) {
            return getBlockImage(block);
        }
        if (imgs.length === 1 && !block.textContent.replace(/<[^>]+>/g, "").trim()) {
            return imgToBase64(imgs[0]);
        }

        // Multiple formula images in a single choice (e.g. vector 1 and vector 2): combine horizontally
        try {
            var items = [];
            var totalW = 0;
            var maxH = 30;

            var host = block.querySelector("label, .form-check-label") || block;
            var nodes = Array.from(host.childNodes);
            if (nodes.length === 0) nodes = [host];

            var testCanvas = document.createElement("canvas");
            var testCtx = testCanvas.getContext("2d");
            testCtx.font = "bold 16px sans-serif";

            for (var ni = 0; ni < nodes.length; ni++) {
                var node = nodes[ni];
                if (node.nodeType === 3) {
                    var txt = (node.textContent || "").replace(/\s+/g, " ").trim();
                    if (txt) {
                        var tw = Math.ceil(testCtx.measureText(txt).width);
                        items.push({ type: "text", text: txt, width: tw + 16, height: 24 });
                        totalW += tw + 16;
                    }
                } else if (node.nodeType === 1) {
                    if (node.tagName === "IMG") {
                        var iw = node.naturalWidth || node.clientWidth || node.width || 50;
                        var ih = node.naturalHeight || node.clientHeight || node.height || 40;
                        items.push({ type: "img", el: node, width: iw, height: ih });
                        totalW += iw + 12;
                        if (ih > maxH) maxH = ih;
                    } else {
                        var subImgs = Array.from(node.querySelectorAll("img"));
                        if (subImgs.length > 0) {
                            for (var si = 0; si < subImgs.length; si++) {
                                var sImg = subImgs[si];
                                var sw = sImg.naturalWidth || sImg.clientWidth || sImg.width || 50;
                                var sh = sImg.naturalHeight || sImg.clientHeight || sImg.height || 40;
                                items.push({ type: "img", el: sImg, width: sw, height: sh });
                                totalW += sw + 12;
                                if (sh > maxH) maxH = sh;
                            }
                        } else {
                            var subTxt = (node.textContent || "").replace(/\s+/g, " ").trim();
                            if (subTxt) {
                                var stw = Math.ceil(testCtx.measureText(subTxt).width);
                                items.push({ type: "text", text: subTxt, width: stw + 16, height: 24 });
                                totalW += stw + 16;
                            }
                        }
                    }
                }
            }

            var hasImgItem = items.some(function(it) { return it.type === "img"; });
            if (hasImgItem && items.length > 1 && totalW > 0 && maxH > 0) {
                var cv = document.createElement("canvas");
                cv.width = totalW + 16;
                cv.height = maxH + 8;
                var ctx = cv.getContext("2d");
                ctx.fillStyle = "#ffffff";
                ctx.fillRect(0, 0, cv.width, cv.height);
                ctx.font = "bold 16px sans-serif";
                ctx.textBaseline = "middle";

                var curX = 8;
                for (var j = 0; j < items.length; j++) {
                    var item = items[j];
                    if (item.type === "img") {
                        var offsetY = Math.round((cv.height - item.height) / 2);
                        ctx.drawImage(item.el, curX, offsetY, item.width, item.height);
                        curX += item.width + 12;
                    } else if (item.type === "text") {
                        ctx.fillStyle = "#1e293b";
                        var textY = Math.round(cv.height / 2);
                        ctx.fillText(item.text, curX + 4, textY);
                        curX += item.width;
                    }
                }
                var b64Comb = cv.toDataURL("image/png");
                if (b64Comb && b64Comb.length > 50) return b64Comb;
            }
        } catch (e) {}

        return imgToBase64(imgs[0]);
    }

    function getExamTitle() {
        var bodyText = document.body ? (document.body.innerText || "") : "";
        var cleanedBodyText = bodyText
            .replace(/Campus Exam[^\r\n<]*Phiên bản[^\r\n<]*/gi, " ")
            .replace(/\[\s*ClassCode\s*:\s*Campus Exam[^\r\n<]*\]/gi, " ");

        // Priority 0: Chuỗi tiêu đề đầy đủ "Kiểm tra cá nhân - [ClassCode: ...]" từ DOM
        var mExactHeader = cleanedBodyText.match(/(Kiểm tra cá nhân\s*[-–—:]\s*\[\s*ClassCode\s*:\s*([^\]]+)\](?:\s*-\s*\[[^\]]+\])*(?:\s*-\s*[^\[\r\n<]+)?)/i);
        if (!mExactHeader && document.title) {
            mExactHeader = document.title.match(/(Kiểm tra cá nhân\s*[-–—:]\s*\[\s*ClassCode\s*:\s*([^\]]+)\](?:\s*-\s*\[[^\]]+\])*(?:\s*-\s*[^\[\r\n<]+)?)/i);
        }
        if (mExactHeader) {
            var rawH = mExactHeader[1].trim();
            rawH = rawH.replace(/\s*\[\d+\.\d+\][\s\d\/:]*$/i, "").trim();
            return rawH;
        }

        var mBracket = cleanedBodyText.match(/(\[\s*ClassCode\s*:\s*([^\]]+)\](?:\s*-\s*\[[^\]]+\])*(?:\s*-\s*[^\[\r\n<]+)?)/i);
        if (mBracket) {
            var rawB = mBracket[1].trim().replace(/\s*\[\d+\.\d+\][\s\d\/:]*$/i, "").trim();
            return "Kiểm tra cá nhân - " + rawB;
        }

        // Priority 1: Match real subject codes like [MAS291], [MAD101], [SWR302], MAS291_SP24
        var mCode = cleanedBodyText.match(/\b([A-Z]{2,4}\d{2,4}[a-zA-Z0-9_\.]*)\b/);
        var subjectCodeFound = mCode ? mCode[1].trim() : "";

        // Priority 2: Scan headers and breadcrumbs, filtering out generic portal footers
        var titleElems = document.querySelectorAll("h1, h2, h3, h4, .title, [class*='title'], [class*='breadcrumb'], [class*='header-title'], #page-header");
        for (var i = 0; i < titleElems.length; i++) {
            var t = getText(titleElems[i]).trim();
            // Filter out generic portal noise
            if (t.includes("Phiên bản") || t.includes("Quyền truy cập") || t.includes("Campus Exam") || t.includes("Safe Exam Browser") || t.includes("SEB Admin")) {
                continue;
            }
            if (t.length >= 4 && (t.includes("Kiểm tra") || t.includes("Thi") || t.includes("Exam") || t.includes("ClassCode") || t.includes("Assignment") || t.includes("Quiz") || t.includes("Test"))) {
                if (subjectCodeFound && !t.includes(subjectCodeFound)) {
                    return "[" + subjectCodeFound + "] " + t;
                }
                return t;
            }
        }

        // Priority 3: Document title cleaned
        var docTitle = (document.title || "").replace(/\s*[-|]\s*Moodle.*$/i, "").trim();
        if (docTitle && docTitle !== "Safe Exam Browser" && !docTitle.includes("Phiên bản") && !docTitle.includes("Campus Exam")) {
            if (subjectCodeFound && !docTitle.includes(subjectCodeFound)) {
                return "[" + subjectCodeFound + "] " + docTitle;
            }
            return docTitle;
        }

        if (subjectCodeFound) return "[" + subjectCodeFound + "] Bài thi trắc nghiệm";
        return "Bài thi trực tuyến";
    }

    // ─────────────────────────────────────────────────────────────────────────
    // EXAM METADATA EXTRACTION (ClassCode, Môn thi, Giám thị, Giờ thi, Countdown)
    // ─────────────────────────────────────────────────────────────────────────
    function extractExamMetadata() {
        var meta = {
            class_code: "",
            subject_code: "",
            proctor_email: "",
            paper_code: "",
            student_account: "",
            campus: "",
            exam_server_time: "",
            remaining_time: ""
        };

        // 1. Quét các phần tử chứa tiêu đề bài thi (ưu tiên phần tử tiêu đề rõ ràng)
        var titleNodes = document.querySelectorAll(".topbar, .topbar span, #topbar, .navbar, .header, header, .header-title, #page-header h1, h1, h2, h3, h4, .page-header-headings, .page-context-header, #page-header, .breadcrumb, [aria-label='breadcrumb'], .breadcrumb-item, .breadcrumb-nav, .title, [class*='title'], [class*='breadcrumb'], [class*='header'], [class*='sub-header'], [class*='info']");
        var fullTitle = "";
        for (var i = 0; i < titleNodes.length; i++) {
            var txt = (titleNodes[i].innerText || titleNodes[i].textContent || "").trim();
            if (txt.includes("Campus Exam") || txt.includes("Phiên bản") || txt.includes("Quyền truy cập STUDENT") || txt.includes("Safe Exam Browser")) {
                continue;
            }
            if (txt.includes("Kiểm tra cá nhân") && txt.includes("ClassCode")) {
                fullTitle = txt;
                break;
            }
            if (txt.includes("ClassCode") || txt.includes("Kiểm tra cá nhân")) {
                if (!fullTitle) fullTitle = txt;
            }
        }
        if (!fullTitle) {
            var rawB = (document.body ? document.body.innerText : "") || document.title || "";
            var mBody = rawB.match(/(Kiểm tra cá nhân\s*[-–—:]\s*\[\s*ClassCode\s*:\s*([^\]]+)\](?:\s*-\s*\[([^\]]+)\])?(?:\s*-\s*([^\[\r\n<]+))?)/i);
            if (mBody) {
                fullTitle = mBody[0];
            } else {
                fullTitle = rawB
                    .replace(/Campus Exam[\s\S]*?Phiên bản[^\r\n<]*/gi, " ")
                    .replace(/\[\s*ClassCode\s*:\s*Campus Exam[^\r\n<]*\]/gi, " ");
            }
        }

        // Trích xuất chuỗi tiêu đề đầy đủ: ví dụ Kiểm tra cá nhân - [ClassCode: IC2114]-[MAE101]-Assignment 2 ở nhà
        var mFull = fullTitle.match(/(Kiểm tra cá nhân\s*[-–—:]\s*\[\s*ClassCode\s*:\s*([^\]]+)\](?:\s*-\s*\[([^\]]+)\])?(?:\s*-\s*([^\[\r\n<]+))?)/i);
        if (!mFull && document.title) {
            mFull = document.title.match(/(Kiểm tra cá nhân\s*[-–—:]\s*\[\s*ClassCode\s*:\s*([^\]]+)\](?:\s*-\s*\[([^\]]+)\])?(?:\s*-\s*([^\[\r\n<]+))?)/i);
        }

        if (mFull) {
            var cleanH = mFull[1].trim().replace(/\s*\[\d+\.\d+\][\s\d\/:]*$/i, "").trim();
            meta.exam_header = cleanH;
            meta.full_class_info = cleanH;
            meta.class_code = mFull[2] ? mFull[2].trim() : cleanH;
            if (mFull[3]) {
                meta.subject_code = mFull[3].trim();
            }
        } else {
            var mBracket = fullTitle.match(/(\[\s*ClassCode\s*:\s*([^\]]+)\](?:\s*-\s*\[([^\]]+)\])?(?:\s*-\s*([^\[\r\n<]+))?)/i);
            if (mBracket) {
                var cleanB = mBracket[1].trim().replace(/\s*\[\d+\.\d+\][\s\d\/:]*$/i, "").trim();
                meta.exam_header = "Kiểm tra cá nhân - " + cleanB;
                meta.full_class_info = cleanB;
                meta.class_code = mBracket[2] ? mBracket[2].trim() : cleanB;
                if (mBracket[3]) {
                    meta.subject_code = mBracket[3].trim();
                }
            }
        }

        // ClassCode đơn lẻ nếu chưa có
        if (!meta.class_code) {
            var mClass = fullTitle.match(/\[?\s*ClassCode\s*:\s*([^\]]+?)\s*\]/i);
            if (mClass) meta.class_code = mClass[1].trim();
        }

        // SubjectCode: ví dụ [MAE101] hoặc [HCM202]
        if (!meta.subject_code) {
            var mSubj = fullTitle.match(/-\[([A-Za-z0-9_.]+)\]/);
            if (!mSubj && meta.exam_header) mSubj = meta.exam_header.match(/-\[([A-Za-z0-9_.]+)\]/);
            if (!mSubj) mSubj = fullTitle.match(/\[([A-Z]{2,4}\d{2,4}[a-zA-Z0-9_\.]*)\]/);
            if (mSubj) {
                meta.subject_code = mSubj[1].trim();
            } else if (meta.class_code) {
                var parts = meta.class_code.replace(/\[|\]/g, "").split(/[\.\-]/);
                if (parts.length > 0) meta.subject_code = parts[0].replace(/ClassCode\s*:\s*/i, "").trim();
            }
        }

        // Proctor email: ví dụ [donnt3@fpt.edu.vn]
        var mEmail = fullTitle.match(/\[([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\]/);
        if (!mEmail && meta.full_class_info) mEmail = meta.full_class_info.match(/\[([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\]/);
        if (mEmail) meta.proctor_email = mEmail[1].trim();

        // Paper UUID / Code: ví dụ [eb09e692-618d-469e-be6a-c230625259cc] hoặc [185]
        var mPaper = fullTitle.match(/\[([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]/);
        if (!mPaper && meta.full_class_info) {
            var mAttempt = meta.full_class_info.match(/-\[([^\]]+)\]$/);
            if (mAttempt && !mAttempt[1].includes("@") && mAttempt[1] !== meta.subject_code) mPaper = mAttempt;
        }
        if (!mPaper) mPaper = fullTitle.match(/\[([a-zA-Z0-9_-]{16,})\]/);
        if (mPaper) meta.paper_code = mPaper[1].trim();

        // Lọc sạch rác portal cho các trường thông tin
        if (/Campus Exam|Phiên bản|Quyền truy cập|Safe Exam Browser/i.test(meta.class_code)) {
            meta.class_code = "";
        }
        if (/Campus Exam|Phiên bản|Quyền truy cập|Safe Exam Browser/i.test(meta.exam_header)) {
            meta.exam_header = "";
        }
        if (/Campus Exam|Phiên bản|Quyền truy cập|Safe Exam Browser/i.test(meta.full_class_info)) {
            meta.full_class_info = "";
        }

        // 2. Quét Header để lấy thời gian thi thực tế và email tài khoản sinh viên
        var headerEls = document.querySelectorAll("header, .header, [class*='navbar'], [class*='topbar'], [class*='user'], [class*='profile'], [class*='account'], body");
        for (var h = 0; h < headerEls.length; h++) {
            var hText = (headerEls[h].innerText || headerEls[h].textContent || "").trim();
            
            // Thời gian server: ví dụ 08:42:28 07/15/2026 hoặc 20:05:44
            if (!meta.exam_server_time) {
                var mTime = hText.match(/(\d{1,2}:\d{2}(?::\d{2})?\s+\d{1,2}[\/-]\d{1,2}[\/-]\d{4})/);
                if (mTime) {
                    meta.exam_server_time = mTime[1].trim();
                } else {
                    var mTimeSimple = hText.match(/(?:Server\s*time|Giờ\s*máy\s*chủ|Giờ\s*hệ\s*thống|Thời\s*gian|Time)?\s*[:]?\s*(\b[0-2]?\d:[0-5]\d:[0-5]\d\b)/i);
                    if (mTimeSimple) meta.exam_server_time = mTimeSimple[1].trim();
                }
            }

            // Email sinh viên & Campus: nguyenlamphuc0310@gmail.com (Exam_FU_HL)
            if (!meta.student_account) {
                var mAcc = hText.match(/([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)(?:\s*\(([^)]+)\))?/i);
                if (mAcc && (!meta.proctor_email || mAcc[1].toLowerCase() !== meta.proctor_email.toLowerCase())) {
                    meta.student_account = mAcc[1].trim();
                    if (mAcc[2]) meta.campus = mAcc[2].trim();
                }
            }
            if (meta.exam_server_time && meta.student_account) break;
        }

        // 3. Quét thời gian còn lại (Remaining time countdown)
        // Hỗ trợ chính xác: "26m : 0s", "1h : 20m : 0s", "45:20", "30 phút 15 giây", "45m"
        var timerRegex = /(\d+\s*(?:h|giờ)\s*:\s*\d+\s*(?:m|phút)\s*:\s*\d+\s*(?:s|giây)|\d+\s*(?:m|phút)\s*:\s*\d+\s*(?:s|giây)|\d+\s*(?:h|giờ)\s*:\s*\d+\s*(?:m|phút)|\d+\s*(?:h|giờ)\s+\d+\s*(?:m|phút)(?:\s+\d+\s*(?:s|giây))?|\d+\s*(?:phút|mins?|m)(?:\s+\d+\s*(?:giây|secs?|s))?|\d{1,2}:\d{2}(?::\d{2})?)/i;

        // Ưu tiên 1: Quét các element timer chuyên biệt
        var timerEls = document.querySelectorAll("#quiz-timer, #quiz-time-left, [role='timer'], [class*='timer'], [class*='countdown'], [id*='timer'], [id*='countdown'], [class*='time-left'], [class*='remaining']");
        for (var t = 0; t < timerEls.length; t++) {
            var tText = (timerEls[t].innerText || timerEls[t].textContent || "").trim();
            var mRem = tText.match(timerRegex);
            if (mRem && mRem[1]) {
                meta.remaining_time = mRem[1].replace(/\s+/g, " ").trim();
                break;
            }
        }

        // Ưu tiên 2: Quét nhãn "Thời gian còn lại" hoặc "Time left" (trong ảnh mẫu: Thời gian còn lại \n 26m : 0s)
        if (!meta.remaining_time) {
            var labelEls = document.querySelectorAll("div, span, p, label, b, strong");
            for (var d = 0; d < labelEls.length; d++) {
                var rawTxt = (labelEls[d].innerText || labelEls[d].textContent || "").trim();
                if (rawTxt.includes("Thời gian còn lại") || rawTxt.includes("Time left")) {
                    var m1 = rawTxt.match(timerRegex);
                    if (m1 && m1[1]) {
                        meta.remaining_time = m1[1].replace(/\s+/g, " ").trim();
                        break;
                    }
                    var sib = labelEls[d].nextElementSibling;
                    if (sib) {
                        var sTxt = (sib.innerText || sib.textContent || "").trim();
                        var m2 = sTxt.match(timerRegex);
                        if (m2 && m2[1]) {
                            meta.remaining_time = m2[1].replace(/\s+/g, " ").trim();
                            break;
                        }
                    }
                    var par = labelEls[d].parentElement;
                    if (par) {
                        var pTxt = (par.innerText || par.textContent || "").trim();
                        var m3 = pTxt.match(timerRegex);
                        if (m3 && m3[1]) {
                            meta.remaining_time = m3[1].replace(/\s+/g, " ").trim();
                            break;
                        }
                    }
                }
            }
        }

        // Ưu tiên 3: Quét fallback toàn bộ body
        if (!meta.remaining_time && document.body) {
            var bText = document.body.innerText || "";
            var mDirect = bText.match(/(\b\d+\s*m\s*:\s*\d+\s*s\b|\b\d+\s*h\s*:\s*\d+\s*m\s*:\s*\d+\s*s\b)/i);
            if (mDirect && mDirect[1]) {
                meta.remaining_time = mDirect[1].replace(/\s+/g, " ").trim();
            } else {
                var mB = bText.match(/(?:Thời gian còn lại|Time left)[\s\:\-]+(\d+\s*m\s*:\s*\d+\s*s|\d+\s*h\s*:\s*\d+\s*m\s*:\s*\d+\s*s|\d{1,2}:\d{2}(?::\d{2})?|\d+\s*(?:phút|mins?|m))/i);
                if (mB && mB[1]) {
                    meta.remaining_time = mB[1].replace(/\s+/g, " ").trim();
                }
            }
        }

        return meta;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // QUESTION TYPE DETECTION
    // ─────────────────────────────────────────────────────────────────────────
    function detectQuestionType(block) {
        if (!block) return "radio";

        // 1. Uu tien tuyet doi: Kiem tra the input thuc te tren giao dien DOM
        var radios = block.querySelectorAll("input[type='radio'], [role='radio'], .ant-radio, input.form-check-input[type='radio']");
        var checks = block.querySelectorAll("input[type='checkbox'], [role='checkbox'], .ant-checkbox, input.form-check-input[type='checkbox']");

        if (radios.length > 0 && checks.length === 0) return "radio";
        if (checks.length > 0 && radios.length === 0) return "checkbox";

        // 2. Kiem tra chi dan de bai cu the (Moodle, FPT Exam, Blackboard, Canvas)
        var txt = (getText(block) || "").toLowerCase();
        if (txt.includes("select one or more") || txt.includes("choose one or more") || 
            txt.includes("chọn một hoặc nhiều") || txt.includes("nhiều đáp án") || 
            txt.includes("select all that apply") || txt.includes("multiple answers") ||
            txt.includes("chọn các đáp án") || txt.includes("chọn tất cả") ||
            txt.includes("có thể chọn nhiều")) {
            return "checkbox";
        }
        if (txt.includes("select one:") || txt.includes("choose one") || 
            txt.includes("choose 1 answer") || txt.includes("chọn một:") || 
            txt.includes("chọn 1 đáp án") || txt.includes("single choice") ||
            txt.includes("chỉ chọn một")) {
            return "radio";
        }

        // 3. Kiem tra cac loai cau hoi khac (Tu luan, dien tu, ghep noi)
        var cls = (block.className || "").toLowerCase();
        if (cls.includes("shortanswer") || cls.includes("short-answer") || cls.includes("numerical")) return "text";
        if (cls.includes("essay") || cls.includes("practical") || cls.includes("pea")) return "essay";
        if (cls.includes("truefalse")) return "radio";

        var selects   = block.querySelectorAll("select");
        var textareas = block.querySelectorAll("textarea, [contenteditable='true'], [class*='rich-editor'], [class*='ql-editor'], .note-editable, iframe");
        var textins   = block.querySelectorAll("input[type='text'], input[type='number'], input[type='email'], input[type='search']");

        if (selects.length > 0)   return "select";
        if (textareas.length > 0) return "essay";
        if (textins.length > 0)   return "text";

        if (checks.length > 0)    return "checkbox";
        return "radio";
    }

    // ─────────────────────────────────────────────────────────────────────────
    // OPTION EXTRACTION
    // ─────────────────────────────────────────────────────────────────────────
    function extractOptions(block, qtype) {
        if (qtype === "text" || qtype === "essay") return [];

        var options = [];
        var ALPHA   = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

        // Ưu tiên 1: Quét trực tiếp toàn bộ thẻ INPUT lựa chọn trong block (Radio / Checkbox)
        // Đây là chân lý (Ground Truth) chính xác 100% số lượng đáp án của đề thi (hỗ trợ 4, 5, 6, 7, 8... đáp án)
        var inputs = Array.from(block.querySelectorAll(
            "input[type='radio'], input[type='checkbox'], [role='radio'], [role='checkbox'], input.form-check-input"
        ));

        if (inputs.length > 0) {
            inputs.forEach(function (inp, idx) {
                try {
                    var container = inp.closest("label, .form-check, .choice, .option, [class*='choice'], [class*='option'], [class*='answer'], tr, li") || inp.parentElement;
                    var label = null;
                    if (inp.id) {
                        try { label = (block.ownerDocument || document).querySelector("label[for='" + inp.id + "']"); } catch(e){}
                    }
                    if (!label && container) {
                        label = container.querySelector("label");
                    }
                    if (!label) {
                        var sib = inp.nextElementSibling;
                        while (sib) {
                            if (sib.tagName === "LABEL" || sib.classList.contains("label") || sib.tagName === "SPAN" || sib.tagName === "DIV") {
                                label = sib;
                                break;
                            }
                            if (sib.tagName === "INPUT") break;
                            sib = sib.nextElementSibling;
                        }
                    }

                    // Lấy text đầy đủ nhất: Ưu tiên bóc tách toàn bộ container của lựa chọn (loại bỏ input)
                    // để không bao giờ bị cụt nếu đáp án chứa nhiều thẻ con (span, font, b, i, p) nằm ngoài thẻ label
                    var tContainer = "";
                    if (container) {
                        try {
                            var cClone = container.cloneNode(true);
                            var inpsInClone = cClone.querySelectorAll("input, [type='radio'], [type='checkbox']");
                            for (var ic = 0; ic < inpsInClone.length; ic++) inpsInClone[ic].remove();
                            tContainer = getText(cClone);
                        } catch (e) {}
                    }
                    var tLabel = label ? getText(label) : "";
                    var host = container || label || inp.parentElement;
                    var t = (tContainer && tContainer.length >= tLabel.length) ? tContainer : (tLabel || getText(host));

                    var img = getOptionImage(host) || (label ? getOptionImage(label) : "") || getOptionImage(inp.parentElement);

                    // Nếu text rỗng và không có ảnh, kiểm tra text của các thẻ con hoặc alt text
                    if (!t && !img && host) {
                        var allImgs = host.querySelectorAll("img");
                        for (var mi = 0; mi < allImgs.length; mi++) {
                            var alt = (allImgs[mi].alt || "").trim();
                            if (alt) { t = alt; break; }
                        }
                    }

                    // Luôn bảo tồn đủ số lượng đáp án (kể cả 5, 6, 7 câu)
                    var cleanText = cleanOptionText(t);
                    if (img && (cleanText === "and" || cleanText === "or" || cleanText === "và" || cleanText === "hoặc")) {
                        cleanText = "";
                    }
                    if (!cleanText && !img) {
                        cleanText = "[Lựa chọn " + (ALPHA[idx] || (idx + 1)) + "]";
                    }

                    options.push({
                        label: ALPHA[idx] || String(idx + 1),
                        text: cleanText,
                        image_base64: img || ""
                    });
                } catch (err) {
                    options.push({
                        label: ALPHA[idx] || String(idx + 1),
                        text: "[Lựa chọn " + (ALPHA[idx] || (idx + 1)) + "]",
                        image_base64: ""
                    });
                }
            });

            if (options.length > 0) return options;
        }

        // Ưu tiên 2: Fallback cho các giao diện custom không dùng thẻ input (chỉ dùng container div/li)
        var containers = Array.from(block.querySelectorAll(
            ".form-check, " +
            ".answer [class*='r'], .answer > div, .answer > li, .answer fieldset > div, .answer table tr, .answer .choice, .answer .option, " +
            ".option, .choice, " +
            "[class*='answeroption'], [class*='option-item'], " +
            "[class*='choice-item'], [class*='answer-item'], " +
            "[class*='radio-wrapper'], [class*='checkbox-wrapper'], " +
            ".ant-radio-wrapper, .ant-checkbox-wrapper, .el-radio, .el-checkbox"
        )).filter(function(el) {
            return !el.parentElement.closest(".form-check, .choice, .option, [class*='choice-item'], [class*='option-item']");
        });

        containers.forEach(function (c, idx) {
            var lblEl = c.querySelector(".form-check-label, label, .text, [class*='text']") || c;
            var t = cleanOptionText(getText(lblEl));
            var img = getOptionImage(c);
            if (img && (t === "and" || t === "or" || t === "và" || t === "hoặc")) {
                t = "";
            }
            if (!t && !img) t = "[Lựa chọn " + (ALPHA[idx] || (idx + 1)) + "]";

            options.push({
                label: ALPHA[idx] || String(idx + 1),
                text: t,
                image_base64: img || ""
            });
        });

        return options;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // QUESTION BLOCK DISCOVERY (Carefully scoped so Question 1 doesn't swallow banner)
    // ─────────────────────────────────────────────────────────────────────────
    function findQuestionBlocks(rootDoc) {
        var doc = rootDoc || document;

        // Skip non-exam URLs (index/lobby/login/account/dashboard)
        var locPath = "";
        try { locPath = (window.location.pathname || "").toLowerCase(); } catch(e){}
        if (locPath.endsWith("/exam/index") || locPath.endsWith("/quizprogress/exam") || locPath.endsWith("/quizprogress") || locPath.includes("/login") || locPath.includes("/account") || locPath.includes("/dashboard")) {
            return [];
        }

        // 1. FPT / LMS specific containers: [id^='question-content-'] or [id*='question-content-']
        var fptCards = doc.querySelectorAll("[id^='question-content-'], [id*='question-content-']");
        if (fptCards.length > 0) {
            var validCards = [];
            for (var f = 0; f < fptCards.length; f++) {
                var c = fptCards[f];
                var t = getText(c);
                if (t.includes("Kích thước chữ") || t.includes("Màu sắc trình đơn") || c.closest(".modal, #submitModal")) continue;
                validCards.push(c);
            }
            if (validCards.length > 0) return validCards;
        }

        // 2. Moodle standard blocks
        var blocks = Array.from(doc.querySelectorAll(".que, .question-block, [class*='question-item'], [class*='question-wrapper']"));
        if (blocks.length > 0) return blocks;

        // 3. Headings matching "CÂU HỎI X" or "QUESTION X"
        var allElems = doc.querySelectorAll("h1, h2, h3, h4, h5, h6, .card-header, [class*='header']");
        var seenContainers = new Set();
        var fptBlocks = [];

        for (var i = 0; i < allElems.length; i++) {
            var el = allElems[i];
            var txt = getText(el);
            if (/(?:CÂU\s*HỎI|CAU\s*HOI|QUESTION)\s*\d+/i.test(txt)) {
                var card = el.closest(".card, [class*='card'], .panel, [class*='panel'], [class*='content'], [class*='box'], form, [id*='question']") || el.parentElement;
                if (card && !seenContainers.has(card)) {
                    var cardTxt = getText(card);
                    if (cardTxt.includes("Kích thước chữ") || card.closest(".modal, #submitModal")) continue;
                    seenContainers.add(card);
                    fptBlocks.push(card);
                }
            }
        }
        if (fptBlocks.length > 0) return fptBlocks;

        // 4. Fallback: Any container holding radio choices (at least 2 options), strictly excluding settings modal
        var radios = doc.querySelectorAll("input[type='radio'], input[type='radio'].form-check-input");
        for (var r = 0; r < radios.length; r++) {
            var radio = radios[r];
            if (radio.closest(".modal, #submitModal, [class*='setting'], [class*='config']")) continue;
            var hostCard = radio.closest(".card, [class*='card'], .panel, form") || radio.parentElement.parentElement;
            if (hostCard && !seenContainers.has(hostCard)) {
                var hTxt = getText(hostCard);
                if (hTxt.includes("Kích thước chữ") || hTxt.includes("Màu sắc thanh trạng thái")) continue;
                var cardRadios = hostCard.querySelectorAll("input[type='radio']");
                if (cardRadios.length >= 2 || /(?:CÂU\s*HỎI|CAU\s*HOI|QUESTION)\s*\d+/i.test(hTxt)) {
                    seenContainers.add(hostCard);
                    fptBlocks.push(hostCard);
                }
            }
        }
        if (fptBlocks.length > 0) return fptBlocks;

        return [];
    }

    function getQuestionIndex(block, fallbackIdx) {
        if (!block) return fallbackIdx;

        // 1. Direct ID match: question-content-0, question-1, q-1
        var idAttr = block.id || "";
        var mId = idAttr.match(/question-content-(\d+)/i);
        if (mId) {
            var numId = parseInt(mId[1], 10);
            if (!isNaN(numId) && numId >= 0) return numId;
        }
        var mId2 = idAttr.match(/(?:question-|q-)(\d+)/i);
        if (mId2) {
            var numId2 = parseInt(mId2[1], 10);
            if (!isNaN(numId2) && numId2 > 0) return numId2 - 1;
        }

        // 2. Heading match on text inside block
        var txt = getText(block);
        var match = txt.match(/(?:CÂU\s*(?:HỎI|SỐ)?|CAU\s*(?:HOI|SO)?|QUESTION|BÀI|BAI|Q)\s*[:.]?\s*(\d+)/i);
        if (match) {
            var n = parseInt(match[1], 10);
            if (!isNaN(n) && n > 0) return n - 1; // 0-based
        }

        // 3. Active question button in sidebar/matrix
        var activeBtn = document.querySelector(".btn-question.btn-primary, .btn-question.active, [id^='btn-question-'].btn-primary");
        if (activeBtn) {
            var bTxt = getText(activeBtn).trim();
            var bNum = parseInt(bTxt, 10);
            if (!isNaN(bNum) && bNum > 0) return bNum - 1;
            var bId = activeBtn.id || "";
            var mbId = bId.match(/btn-question-(\d+)/i);
            if (mbId) return parseInt(mbId[1], 10);
        }

        var qnoEl = block.querySelector(".qno, [class*='qno']");
        if (qnoEl) {
            var num = parseInt(getText(qnoEl).replace(/\D+/g, ""), 10);
            if (!isNaN(num) && num > 0) return num - 1;
        }
        var noEl = block.querySelector(".no, .question-number, [class*='question-number']");
        if (noEl) {
            var m = getText(noEl).match(/(\d+)/);
            if (m) {
                var num2 = parseInt(m[1], 10);
                if (!isNaN(num2) && num2 > 0) return num2 - 1;
            }
        }

        return fallbackIdx;
    }

    function extractQuestionStem(block) {
        if (!block) return "";

        // Priority 1: FPT specific stem containers (hỗ trợ tất cả các khối đề bài liên tiếp)
        var fptStemEls = Array.from(block.querySelectorAll(".card-body.border-bottom, .card-body.stem, [class*='stem-content']"));
        if (fptStemEls.length > 0) {
            var stemParts = [];
            var altTexts = [];
            fptStemEls.forEach(function (fptEl) {
                var stemClone = fptEl.cloneNode(true);
                var noise1 = stemClone.querySelectorAll("style, script, .btn-mark, .timer, [class*='timer']");
                for (var i = 0; i < noise1.length; i++) noise1[i].remove();

                var mathImgs = stemClone.querySelectorAll("img");
                for (var m = 0; m < mathImgs.length; m++) {
                    var alt = (mathImgs[m].alt || "").trim();
                    if (alt && alt.length > 1 && !/^(?:image|hinh|ảnh)$/i.test(alt)) {
                        altTexts.push(alt);
                    }
                }
                var partText = cleanStemText(getText(stemClone));
                if (partText) stemParts.push(partText);
            });

            var s = stemParts.join("\n").trim();
            if (altTexts.length > 0 && (!s || s.length < 5)) {
                s = (s ? s + " " : "") + altTexts.join(" ");
            }
            if (s.length >= 2) return s;

            if (block.querySelector(".card-body.border-bottom img, .card-body.border-bottom canvas, .card-body.border-bottom svg")) {
                return "[Đề bài dạng hình ảnh / biểu đồ]";
            }
        }

        // Priority 2: Moodle qtext (hỗ trợ mọi khối qtext / question-text liên tiếp)
        var qtEls = Array.from(block.querySelectorAll(".qtext, .question-text, .formulation .qtext, .stem, [class*='qtext'], [class*='question-text']"));
        if (qtEls.length > 0) {
            var qParts = [];
            qtEls.forEach(function (qtEl) {
                var qtClone = qtEl.cloneNode(true);
                var noiseQt = qtClone.querySelectorAll("style, script");
                for (var i = 0; i < noiseQt.length; i++) noiseQt[i].remove();
                var partQs = cleanStemText(getText(qtClone));
                if (partQs) qParts.push(partQs);
            });
            var qs = qParts.join("\n").trim();
            if (qs.length >= 2) return qs;
            if (block.querySelector(".qtext img, .question-text img, canvas, svg")) return "[Đề bài dạng hình ảnh / biểu đồ]";
        }

        // Priority 3: General card clone - bóc tách toàn bộ card trừ khu vực options
        try {
            var clone = block.cloneNode(true);
            var noise = clone.querySelectorAll(".btn-mark, .timer, [class*='timer'], [id*='timer'], [class*='countdown'], .notice, [class*='notice'], .instruction, [class*='instruction'], style, script, noscript, xml, meta, link");
            for (var n = 0; n < noise.length; n++) noise[n].remove();

            var allHeaders = clone.querySelectorAll("h1, h2, h3, h4, h5, h6, .card-header, [class*='card-header']");
            for (var h = 0; h < allHeaders.length; h++) {
                var ht = getText(allHeaders[h]);
                if (/(?:CÂU\s*HỎI|CAU\s*HOI|QUESTION)\s*\d+/i.test(ht)) {
                    allHeaders[h].remove();
                }
            }

            var inputsInClone = clone.querySelectorAll(
                "input, textarea, button, " +
                ".form-check, .answer, .options, .choices, [class*='choice'], [class*='option'], [class*='answer'], " +
                "[class*='radio'], [role='radio'], [role='checkbox'], " +
                ".ant-radio-wrapper, .el-radio"
            );
            for (var k = 0; k < inputsInClone.length; k++) {
                inputsInClone[k].remove();
            }

            var stem = cleanStemText(getText(clone));
            if (stem.length >= 3) return stem;
        } catch (e) {}

        // Never fall back to getText(block) if it contains options (prevents option leak into stem)
        if (block.querySelector("img, canvas, svg")) {
            return "[Đề bài dạng hình ảnh / biểu đồ]";
        }
        return "";
    }

    // ─────────────────────────────────────────────────────────────────────────
    // MULTI-PAGE EXAM CRAWLER
    // ─────────────────────────────────────────────────────────────────────────
    var crawledUrls = new Set();

    function crawlOtherExamPages() {
        try {
            var pageLinks = document.querySelectorAll("a[href*='page='], a[href*='attempt.php'], .pagination a, .page-link, .qnbutton");
            pageLinks.forEach(function (a) {
                var href = a.href;
                if (!href || href.startsWith("javascript:") || href.includes("#") || crawledUrls.has(href)) return;
                if (href.includes("summary") || href.includes("processattempt") || href.includes("logout")) return;
                if (href === window.location.href) return;

                crawledUrls.add(href);
                fetch(href, { credentials: "include" })
                    .then(function (res) { return res.text(); })
                    .then(function (html) {
                        try {
                            var parser = new DOMParser();
                            var doc = parser.parseFromString(html, "text/html");
                            var blocks = findQuestionBlocks(doc);
                            blocks.forEach(function (b, i) {
                                var qIdx = getQuestionIndex(b, i);
                                var qtype = detectQuestionType(b);
                                var opts = extractOptions(b, qtype);
                                var stemImg = getStemImage(b);
                                var stemText = extractQuestionStem(b);
                                if (!stemText && stemImg) stemText = "[Câu hỏi dạng hình ảnh / biểu đồ]";
                                if (!stemText && opts.length > 0) stemText = "Câu hỏi " + (qIdx + 1);
                                if (stemText || opts.length > 0) {
                                    accumulatedDomQuestions[qIdx] = {
                                        question_index: qIdx,
                                        question_text: cleanStemText(stemText),
                                        question_type: qtype,
                                        options: opts,
                                        image_base64: stemImg,
                                        current_answer: ""
                                    };
                                }
                            });
                            persistQuestions();
                        } catch (err) {}
                    })
                    .catch(function () {});
            });
        } catch (e) {}
    }

    // ─────────────────────────────────────────────────────────────────────────
    // AUTOMATIC FULL EXAM SWEEPER (Iterates all 60 question buttons in seconds)
    // ─────────────────────────────────────────────────────────────────────────
    var isSweeping = false;
    function sweepAllQuestions(force, onComplete) {
        if (isSweeping) return;
        isSweeping = true;
        console.log("[SEB-Sync] Starting sweep using Next/Prev buttons & matrix...");

        extractQuestions();

        var nextBtn = document.querySelector("#btn-next-question, .btn-next-question");
        var prevBtn = document.querySelector("#btn-previous-question, .btn-previous-question");
        var matrixBtns = document.querySelectorAll(".btn-question, [id^='btn-question-']");

        // Strategy A: Use Prev to rewind to Q1, then Next to sweep forward through all 60
        if (nextBtn && prevBtn) {
            var rewindCount = 0;
            var rewindTimer = setInterval(function () {
                var isPrevDisabled = prevBtn.hasAttribute("disabled") || prevBtn.disabled || prevBtn.classList.contains("disabled");
                if (isPrevDisabled || rewindCount > 65) {
                    clearInterval(rewindTimer);
                    extractQuestions();
                    var fwdCount = 0;
                    var fwdTimer = setInterval(function () {
                        extractQuestions();
                        var isNextDisabled = nextBtn.hasAttribute("disabled") || nextBtn.disabled || nextBtn.classList.contains("disabled");
                        if (isNextDisabled || fwdCount > 65) {
                            clearInterval(fwdTimer);
                            isSweeping = false;
                            extractQuestions();
                            persistQuestions();
                            syncToServer();
                            console.log("[SEB-Sync] Full sweep complete! Total accumulated: " + Object.keys(accumulatedDomQuestions).length);
                            if (onComplete) onComplete();
                            return;
                        }
                        try { nextBtn.click(); } catch(e) {}
                        fwdCount++;
                    }, 120);
                    return;
                }
                try { prevBtn.click(); } catch(e) {}
                rewindCount++;
            }, 60);
            return;
        }

        // Strategy B: Fallback to clicking all matrix buttons
        if (matrixBtns && matrixBtns.length > 0) {
            var mIdx = 0;
            var mTimer = setInterval(function () {
                if (mIdx >= matrixBtns.length) {
                    clearInterval(mTimer);
                    isSweeping = false;
                    extractQuestions();
                    persistQuestions();
                    syncToServer();
                    if (onComplete) onComplete();
                    return;
                }
                try {
                    matrixBtns[mIdx].click();
                    setTimeout(extractQuestions, 60);
                } catch(e) {}
                mIdx++;
            }, 120);
            return;
        }

        isSweeping = false;
        if (onComplete) onComplete();
    }
    window.__SEB_SWEEP_ALL_QUESTIONS__ = sweepAllQuestions;

    // ─────────────────────────────────────────────────────────────────────────
    // QUESTION EXTRACTION (Main)
    // ─────────────────────────────────────────────────────────────────────────
    function extractQuestions() {
        checkAndResetIfNewExam();
        var fullQuestions = interceptedQuestions.length > 1 ? interceptedQuestions : [];
        if (fullQuestions.length > 1) {
            var domBlocks = findQuestionBlocks();
            if (domBlocks.length > 0) {
                var curBlock = domBlocks[0];
                var curIdx = getQuestionIndex(curBlock, 0);
                var curType = detectQuestionType(curBlock);
                var curOpts = extractOptions(curBlock, curType);
                var curAns = getCurrentStudentAnswer(curBlock, curType, curOpts);
                var curStemImg = getStemImage(curBlock);
                for (var q = 0; q < fullQuestions.length; q++) {
                    if (fullQuestions[q].question_index === curIdx) {
                        fullQuestions[q].current_answer = curAns;
                        if (curStemImg && curStemImg.length > 20) {
                            fullQuestions[q].image_base64 = curStemImg;
                        }
                        if (curOpts && curOpts.length > 0) {
                            for (var oi = 0; oi < curOpts.length; oi++) {
                                if (curOpts[oi].image_base64 && fullQuestions[q].options && fullQuestions[q].options[oi]) {
                                    fullQuestions[q].options[oi].image_base64 = curOpts[oi].image_base64;
                                }
                            }
                        }
                        accumulatedDomQuestions[curIdx] = fullQuestions[q];
                        break;
                    }
                }
            }
            persistQuestions();
            return fullQuestions;
        }

        // DOM extraction for currently visible questions
        var queBlocks = findQuestionBlocks();
        queBlocks.forEach(function (block, idx) {
            var qtype = detectQuestionType(block);
            var options = extractOptions(block, qtype);
            var stemImage = getStemImage(block);
            var questionText = extractQuestionStem(block);
            var qIndex = getQuestionIndex(block, idx);

            // Ignore settings modal or invalid text
            if (questionText && (questionText.includes("Kích thước chữ") || questionText.includes("Màu sắc trình đơn"))) {
                return;
            }

            // If questionText accidentally matches the concatenated option texts, clean it
            if (options.length > 0 && questionText) {
                var allOptTexts = options.map(function(o) { return o.text; }).filter(Boolean).join(" ");
                if (allOptTexts.length > 10 && questionText.trim() === allOptTexts.trim()) {
                    questionText = stemImage ? "[Đề bài dạng hình ảnh / biểu đồ]" : ("Câu hỏi " + (qIndex + 1));
                }
            }

            if (!questionText || questionText.length < 2) {
                if (stemImage) {
                    questionText = "[Câu hỏi dạng hình ảnh / biểu đồ]";
                } else if (options.length > 0) {
                    questionText = "Câu hỏi " + (qIndex + 1);
                } else {
                    return;
                }
            }

            // Never extract a bogus question with 0 options and placeholder image text
            if ((!options || options.length === 0) && (questionText.includes("[Đề bài dạng hình ảnh") || questionText.includes("[Câu hỏi dạng hình ảnh"))) {
                if (qtype !== "essay" && qtype !== "text") return;
            }

            // Bảo toàn ảnh đề và ảnh đáp án nếu lần quét này ảnh đang render dở dang
            var prevItem = accumulatedDomQuestions[qIndex];
            if (!stemImage && prevItem && prevItem.image_base64) {
                stemImage = prevItem.image_base64;
            }
            if (options.length > 0 && prevItem && prevItem.options) {
                options.forEach(function (opt, oi) {
                    if (!opt.image_base64 && prevItem.options[oi] && prevItem.options[oi].image_base64) {
                        opt.image_base64 = prevItem.options[oi].image_base64;
                    }
                });
            }

            var currentAnswer = getCurrentStudentAnswer(block, qtype, options);

            accumulatedDomQuestions[qIndex] = {
                question_index:   qIndex,
                question_text:    questionText.slice(0, 1500),
                question_type:    qtype,
                options:          options,
                image_base64:     stemImage,
                current_answer:   currentAnswer,
            };
        });

        persistQuestions();

        var results = Object.values(accumulatedDomQuestions);
        // Exclude settings modal questions
        results = results.filter(function(q) {
            return !q.question_text.includes("Kích thước chữ") && !q.question_text.includes("Màu sắc trình đơn");
        });
        results.sort(function (a, b) { return a.question_index - b.question_index; });
        return results;
    }

    function getCurrentStudentAnswer(block, qtype, options) {
        var ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
        if (qtype === "radio") {
            var checked = block.querySelector("input[type='radio']:checked, input.form-check-input[type='radio']:checked");
            if (checked) {
                var radios = block.querySelectorAll("input[type='radio'], input.form-check-input[type='radio']");
                for (var i = 0; i < radios.length; i++) {
                    if (radios[i] === checked) return (options[i] && options[i].label) ? options[i].label : (ALPHA[i] || String(i));
                }
            }
            // Support custom radio selections without native inputs (e.g. .selected, .active, .checked, aria-checked="true")
            var customChoices = Array.from(block.querySelectorAll(
                ".form-check, .answer > div, .answer > li, .option, .choice, [class*='choice-item'], [class*='option-item'], [role='radio'], .ant-radio-wrapper, .el-radio"
            )).filter(function(el) {
                return !el.parentElement.closest(".form-check, .choice, .option, [class*='choice-item'], [class*='radio-wrapper']");
            });
            for (var c = 0; c < customChoices.length; c++) {
                var el = customChoices[c];
                var isSel = el.classList.contains("selected") || el.classList.contains("active") || el.classList.contains("checked") ||
                            el.classList.contains("ant-radio-wrapper-checked") || el.getAttribute("aria-checked") === "true" ||
                            el.querySelector("input:checked, .ant-radio-checked, [aria-checked='true'], .checked, .selected");
                if (isSel) {
                    return (options[c] && options[c].label) ? options[c].label : (ALPHA[c] || String(c));
                }
            }
            return "";
        }

        if (qtype === "checkbox") {
            var labels = [];
            var checks = block.querySelectorAll("input[type='checkbox'], input.form-check-input[type='checkbox']");
            if (checks.length > 0) {
                checks.forEach(function (c, i) {
                    if (c.checked) {
                        var lbl = (options[i] && options[i].label) ? options[i].label : (ALPHA[i] || String(i));
                        labels.push(lbl);
                    }
                });
            } else {
                var customChecks = Array.from(block.querySelectorAll(
                    ".form-check, [role='checkbox'], .ant-checkbox, .ant-checkbox-wrapper, .choice, .option, [class*='choice-item'], .el-checkbox"
                )).filter(function(el) {
                    return !el.parentElement.closest(".form-check, .choice, .option, [class*='choice-item']");
                });
                customChecks.forEach(function (c, i) {
                    var isSel = c.classList.contains("selected") || c.classList.contains("active") || c.classList.contains("checked") ||
                                c.classList.contains("ant-checkbox-checked") || c.getAttribute("aria-checked") === "true";
                    if (isSel) {
                        var lbl = (options[i] && options[i].label) ? options[i].label : (ALPHA[i] || String(i));
                        labels.push(lbl);
                    }
                });
            }
            return Array.from(new Set(labels)).join(",");
        }

        if (qtype === "text") {
            var inp = block.querySelector("input[type='text'], input[type='number'], input[type='email']");
            return inp ? (inp.value || "").trim() : "";
        }

        if (qtype === "essay") {
            var ta = block.querySelector("textarea, [contenteditable='true']");
            if (!ta) {
                var ifr = block.querySelector("iframe");
                if (ifr) {
                    try {
                        var idoc = ifr.contentDocument || ifr.contentWindow.document;
                        return idoc && idoc.body ? idoc.body.innerText.trim() : "";
                    } catch(e) {}
                }
            }
            return ta ? (ta.value || ta.innerText || "").trim() : "";
        }

        return "";
    }

    function triggerChoiceSelect(container, inp, lbl) {
        var clickTarget = inp || lbl || container;
        if (!clickTarget) return;

        try { clickTarget.scrollIntoView({ behavior: 'auto', block: 'nearest' }); } catch(e){}

        var evtOpts = { bubbles: true, cancelable: true, view: window };
        try { clickTarget.dispatchEvent(new PointerEvent("pointerdown", evtOpts)); } catch(e){}
        try { clickTarget.dispatchEvent(new MouseEvent("mousedown", evtOpts)); } catch(e){}
        try { clickTarget.dispatchEvent(new PointerEvent("pointerup", evtOpts)); } catch(e){}
        try { clickTarget.dispatchEvent(new MouseEvent("mouseup", evtOpts)); } catch(e){}
        try { clickTarget.click(); } catch(e){}

        if (inp) {
            if (!inp.checked) {
                try {
                    var nativeChecked = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "checked");
                    if (nativeChecked && nativeChecked.set) {
                        nativeChecked.set.call(inp, true);
                    } else {
                        inp.checked = true;
                    }
                } catch(e) { inp.checked = true; }
            }
            inp.dispatchEvent(new Event("input",  { bubbles: true }));
            inp.dispatchEvent(new Event("change", { bubbles: true }));
        }

        if (container) {
            container.classList.add("active", "checked", "selected");
            if (container.hasAttribute("role")) container.setAttribute("aria-checked", "true");
            var customIcons = container.querySelectorAll(".ant-radio, .custom-control-input, [class*='radio-inner']");
            for (var i = 0; i < customIcons.length; i++) {
                customIcons[i].classList.add("ant-radio-checked", "active", "checked");
            }
        }
        if (lbl && lbl !== container) {
            lbl.classList.add("active", "checked", "selected");
        }
    }


    function triggerElementClick(el) {
        if (!el) return;
        var inp = el.tagName === "INPUT" ? el : el.querySelector("input");
        var container = el.tagName === "INPUT" ? el.closest(".form-check, .choice, .option") : el;
        var lbl = (inp && inp.id) ? (el.ownerDocument || document).querySelector("label[for='" + inp.id + "']") : (container ? container.querySelector("label") : null);
        triggerChoiceSelect(container, inp, lbl);
    }

    function setCheckboxState(chk, shouldCheck) {
        if (!chk) return;
        var inp = chk.tagName === "INPUT" ? chk : chk.querySelector("input[type='checkbox']");
        var clickTarget = inp || chk;
        if (inp) {
            if (inp.checked !== shouldCheck) {
                var evtOpts = { bubbles: true, cancelable: true, view: window };
                try { clickTarget.dispatchEvent(new PointerEvent("pointerdown", evtOpts)); } catch(e){}
                try { clickTarget.dispatchEvent(new MouseEvent("mousedown", evtOpts)); } catch(e){}
                try { clickTarget.dispatchEvent(new PointerEvent("pointerup", evtOpts)); } catch(e){}
                try { clickTarget.dispatchEvent(new MouseEvent("mouseup", evtOpts)); } catch(e){}
                clickTarget.click();
                if (inp.checked !== shouldCheck) {
                    try {
                        var nativeChecked = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "checked");
                        if (nativeChecked && nativeChecked.set) nativeChecked.set.call(inp, shouldCheck);
                        else inp.checked = shouldCheck;
                    } catch(e) { inp.checked = shouldCheck; }
                }
                inp.dispatchEvent(new Event("input",  { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
            }
        } else {
            var isChecked = chk.classList.contains("ant-checkbox-checked") || chk.classList.contains("selected") || chk.getAttribute("aria-checked") === "true";
            if (isChecked !== shouldCheck) {
                chk.click();
            }
        }
    }

    function applyAnswerForQuestion(block, qtype, answer) {
        if (!block || answer === undefined || answer === null || String(answer).trim() === "") return;
        var ansStr = String(answer).trim();

        // 1. Radio (Single Choice / True-False) - Any number of choices: A, B, C, D, E, F, G, H...
        if (qtype === "radio") {
            // Bỏ chọn toàn bộ đáp án cũ trước khi điền đáp án của admin
            var allOldRadios = block.querySelectorAll("input[type='radio'], input.form-check-input[type='radio']");
            allOldRadios.forEach(function (r) {
                try {
                    var nativeChecked = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "checked");
                    if (nativeChecked && nativeChecked.set) nativeChecked.set.call(r, false);
                    else r.checked = false;
                } catch(e) { r.checked = false; }
            });
            var allOldContainers = block.querySelectorAll(
                ".form-check, .choice, .option, [class*='choice-item'], [class*='option-item'], [role='radio'], .ant-radio-wrapper, .el-radio, label"
            );
            allOldContainers.forEach(function (c) {
                c.classList.remove("active", "checked", "selected", "ant-radio-wrapper-checked");
                c.removeAttribute("aria-checked");
                var icons = c.querySelectorAll(".ant-radio, .custom-control-input, [class*='radio-inner']");
                for (var ic = 0; ic < icons.length; ic++) {
                    icons[ic].classList.remove("ant-radio-checked", "active", "checked");
                }
            });

            var targetIdx = -1;
            var targetLetter = "";
            var isTrueFalse = /^(true|false|đúng|sai|t|f)$/i.test(ansStr);

            if (/^\d+$/.test(ansStr)) {
                targetIdx = parseInt(ansStr, 10);
                targetLetter = targetIdx < 26 ? String.fromCharCode(65 + targetIdx) : "";
            } else {
                var mLetter = ansStr.match(/^\s*(?:option|lựa chọn|đáp án)?\s*[\(\[]?([A-Za-z])[\)\]\.\:\s]*$/i);
                if (mLetter) {
                    targetLetter = mLetter[1].toUpperCase();
                    targetIdx = targetLetter.charCodeAt(0) - 65;
                }
            }

            var radios = Array.from(block.querySelectorAll("input[type='radio'], input.form-check-input[type='radio']"));
            var clicked = false;

            // ƯU TIÊN 1 TUYỆT ĐỐI: Dùng trực tiếp radios[targetIdx]!
            // extractOptions quét chính xác các thẻ input theo thứ tự DOM để gán nhãn A, B, C, D...
            // Do đó radios[targetIdx] CHÍNH XÁC 100% là input của đáp án admin đã chọn (0=A, 1=B, 2=C, 3=D, 4=E, 5=F, 6=G...)!
            if (targetIdx >= 0 && targetIdx < radios.length) {
                var rInp = radios[targetIdx];
                var rContainer = rInp.closest("label, .form-check, .choice, .option, [class*='choice-item'], [class*='option-item'], tr, li") || rInp.parentElement;
                var rLbl = (rInp.id ? (block.ownerDocument || document).querySelector("label[for='" + rInp.id + "']") : null) || (rContainer ? rContainer.querySelector("label") : null);
                triggerChoiceSelect(rContainer, rInp, rLbl);
                clicked = true;
                return;
            }

            // Ưu tiên 2: Fallback cho giao diện custom không dùng thẻ input radio
            if (!clicked && radios.length === 0) {
                var customRadios = Array.from(block.querySelectorAll(
                    "[role='radio'], .ant-radio-wrapper, .el-radio, .choice-item, .option-item, .form-check"
                )).filter(function(el) {
                    return !el.parentElement.closest("[role='radio'], .ant-radio-wrapper, .el-radio, .choice-item, .option-item, .form-check");
                });

                if (targetIdx >= 0 && targetIdx < customRadios.length) {
                    var cContainer = customRadios[targetIdx];
                    var cInp = cContainer.querySelector("input") || cContainer;
                    var cLbl = cContainer.querySelector("label") || cContainer;
                    triggerChoiceSelect(cContainer, cInp, cLbl);
                    clicked = true;
                    return;
                }
            }

            // Ưu tiên 3: Khớp theo nội dung text (chỉ áp dụng khi là Đúng/Sai hoặc text chuỗi dài không có index)
            if (!clicked && (isTrueFalse || ansStr.length > 2)) {
                var searchTargets = radios.length > 0 ? radios : block.querySelectorAll("label, .form-check, .choice, .option");
                var matchTarget = ansStr.toLowerCase();
                for (var si = 0; si < searchTargets.length; si++) {
                    var sEl = searchTargets[si];
                    var sHost = sEl.closest("label, .form-check, .choice, .option, tr, li") || sEl.parentElement;
                    var sText = getText(sHost).trim().toLowerCase();
                    if (sText.includes(matchTarget) ||
                        (isTrueFalse && ((matchTarget === "true" || matchTarget === "đúng") && (sText.includes("true") || sText.includes("đúng")))) ||
                        (isTrueFalse && ((matchTarget === "false" || matchTarget === "sai") && (sText.includes("false") || sText.includes("sai"))))) {
                        var sInp = sEl.tagName === "INPUT" ? sEl : sHost.querySelector("input");
                        var sLbl = (sInp && sInp.id ? (block.ownerDocument || document).querySelector("label[for='" + sInp.id + "']") : null) || sHost.querySelector("label") || sHost;
                        triggerChoiceSelect(sHost, sInp, sLbl);
                        clicked = true;
                        break;
                    }
                }
            }
            return;
        }

        // 2. Checkbox (Multiple Choice) - Supports 5, 6, 7, 8+ choices: "A, C, E", "0, 2, 4", "B, D, F"
        if (qtype === "checkbox") {
            var rawParts = ansStr.split(/[,;\n]/).map(function (s) { return s.trim(); }).filter(Boolean);
            var targetIdxs = [];
            var targetLetters = [];
            var targetTexts = [];

            rawParts.forEach(function (p) {
                var cleanP = p.replace(/^[\(\[\s]+|[\)\]\.\:\s]+$/g, "").trim();
                if (/^\d+$/.test(cleanP)) {
                    var numIdx = parseInt(cleanP, 10);
                    targetIdxs.push(numIdx);
                    if (numIdx < 26) targetLetters.push(String.fromCharCode(65 + numIdx));
                } else if (/^[A-Za-z]$/.test(cleanP)) {
                    var ltr = cleanP.toUpperCase();
                    targetLetters.push(ltr);
                    targetIdxs.push(ltr.charCodeAt(0) - 65);
                } else if (cleanP) {
                    targetTexts.push(cleanP.toLowerCase());
                }
            });

            var checks = block.querySelectorAll("input[type='checkbox'], input.form-check-input[type='checkbox']");
            if (checks.length > 0) {
                checks.forEach(function (chk, i) {
                    var parent = chk.closest("label, .form-check, [class*='choice'], tr, li") || chk.parentElement;
                    var cText = parent ? getText(parent).toLowerCase() : "";
                    var letterMatch = cText.match(/^\s*[\(\[]?([A-Z])[\)\]\.\:\-\s]/i);
                    var chkLetter = letterMatch ? letterMatch[1].toUpperCase() : "";

                    var shouldCheck = targetIdxs.indexOf(i) !== -1 ||
                                      (chkLetter && targetLetters.indexOf(chkLetter) !== -1) ||
                                      targetTexts.some(function(t) { return cText.includes(t); });
                    setCheckboxState(chk, shouldCheck);
                });
            } else {
                var checkContainers = block.querySelectorAll(
                    ".form-check, [role='checkbox'], .ant-checkbox, .ant-checkbox-wrapper, .choice, .option, [class*='choice-item'], [class*='option-item'], [class*='checkbox-wrapper']"
                );
                checkContainers.forEach(function (cBox, i) {
                    var cText = getText(cBox).toLowerCase();
                    var letterMatch = cText.match(/^\s*[\(\[]?([A-Z])[\)\]\.\:\-\s]/i);
                    var chkLetter = letterMatch ? letterMatch[1].toUpperCase() : "";

                    var shouldCheck = targetIdxs.indexOf(i) !== -1 ||
                                      (chkLetter && targetLetters.indexOf(chkLetter) !== -1) ||
                                      targetTexts.some(function(t) { return cText.includes(t); });
                    setCheckboxState(cBox, shouldCheck);
                });
            }
            return;
        }

        // 3. Select / Dropdown / Matching Questions
        if (qtype === "select" || block.querySelectorAll("select").length > 0) {
            var selects = block.querySelectorAll("select");
            if (selects.length > 0) {
                var parts = ansStr.includes(";") ? ansStr.split(";") : (ansStr.includes("\n") ? ansStr.split("\n") : (selects.length > 1 && ansStr.includes(",") ? ansStr.split(",") : [ansStr]));
                selects.forEach(function (sel, sIdx) {
                    var targetVal = (parts[sIdx] !== undefined ? parts[sIdx] : parts[0]).trim().toLowerCase();
                    for (var o = 0; o < sel.options.length; o++) {
                        var optText = (sel.options[o].text || "").toLowerCase();
                        var optVal = (sel.options[o].value || "").toLowerCase();
                        if (optText.includes(targetVal) || optVal === targetVal || String(o) === targetVal) {
                            sel.selectedIndex = o;
                            sel.dispatchEvent(new Event("change", { bubbles: true }));
                            sel.dispatchEvent(new Event("input",  { bubbles: true }));
                            break;
                        }
                    }
                });
            }
            if (qtype === "select") return;
        }

        // 4. Text / Fill in the blank (Single or Multiple inputs in one question)
        if (qtype === "text") {
            var inps = block.querySelectorAll("input[type='text'], input[type='number'], input[type='email'], input[type='search'], input:not([type]), .ant-input");
            if (inps.length > 0) {
                var parts = ansStr.includes(";") ? ansStr.split(";") : (ansStr.includes("\n") ? ansStr.split("\n") : (inps.length > 1 && ansStr.includes(",") ? ansStr.split(",") : [ansStr]));
                inps.forEach(function (inp, i) {
                    var val = (parts[i] !== undefined ? parts[i] : parts[0]).trim();
                    try {
                        var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                        nativeSetter.call(inp, val);
                    } catch (e) { inp.value = val; }
                    inp.dispatchEvent(new Event("input",  { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                });
            }
            return;
        }

        // 5. Essay / Writing / Code / Rich-Text (Textarea, ContentEditable, TinyMCE iframe)
        if (qtype === "essay") {
            var ta = block.querySelector("textarea, [contenteditable='true']");
            if (ta) {
                if (ta.tagName === "TEXTAREA") {
                    try {
                        var nativeSetter2 = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                        nativeSetter2.call(ta, ansStr);
                    } catch (e) { ta.value = ansStr; }
                } else {
                    ta.innerText = ansStr;
                }
                ta.dispatchEvent(new Event("input",  { bubbles: true }));
                ta.dispatchEvent(new Event("change", { bubbles: true }));
            }

            // Support TinyMCE / CKEditor WYSIWYG iframes
            var iframes = block.querySelectorAll("iframe");
            iframes.forEach(function (ifr) {
                try {
                    var idoc = ifr.contentDocument || ifr.contentWindow.document;
                    if (idoc && idoc.body) {
                        idoc.body.innerHTML = ansStr.replace(/\n/g, "<br>");
                        idoc.body.dispatchEvent(new Event("input",  { bubbles: true }));
                        idoc.body.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                } catch(e) {}
            });
            return;
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // DYNAMIC GLOBAL CLICK & INTERCEPTOR (Free manual choice, click question text to apply admin answer)
    // ─────────────────────────────────────────────────────────────────────────
    function setupGlobalClickToAnswer() {
        if (window.__sebGlobalClickBound__) return;
        window.__sebGlobalClickBound__ = true;

        // Khi DOM thay đổi (ví dụ học sinh chuyển câu), cập nhật câu hỏi hiển thị
        try {
            var debounceTimer = null;
            var observer = new MutationObserver(function () {
                if (debounceTimer) clearTimeout(debounceTimer);
                debounceTimer = setTimeout(function () {
                    extractQuestions();
                }, 80);
            });
            observer.observe(document.body, { childList: true, subtree: true });
        } catch(e) {}

        // Lắng nghe khi học sinh tự click chọn hoặc sửa đáp án của mình
        document.addEventListener("change", function (e) {
            if (e && e.isTrusted === false) return;
            setTimeout(function () {
                extractQuestions();
                syncToServer();
            }, 40);
        }, true);

        document.addEventListener("input", function (e) {
            if (e && e.isTrusted === false) return;
            setTimeout(function () {
                extractQuestions();
                syncToServer();
            }, 80);
        }, true);

        document.addEventListener("click", function (e) {
            var target = e.target;
            if (!target) return;

            // 1. Nếu click nút điều hướng (số câu trong bảng ma trận hoặc nút Tiếp theo / Trước)
            var btnText = getText(target);
            if (/^\d{1,3}$/.test(btnText) || target.classList.contains("btn-question") || target.closest(".btn-question") ||
                /Tiếp|Trước|Tải lại|Next|Prev|Forward|Back/i.test(btnText) || target.closest("#btn-next-question, #btn-previous-question, .btn-next-question, .btn-previous-question")) {
                setTimeout(function () { 
                    extractQuestions(); 
                    syncToServer(); 
                }, 80);
                setTimeout(function () { 
                    extractQuestions(); 
                    syncToServer(); 
                }, 350);
                return;
            }

            // 2. NẾU HỌC SINH CLICK VÀO LỰA CHỌN ĐÁP ÁN (radio, checkbox):
            // Cho phép học sinh sửa tự do, TUYỆT ĐỐI KHÔNG ghi đè đáp án admin vào đây!
            var isOptionClick = !!(
                target.tagName === "INPUT" ||
                target.closest("input[type='radio'], input[type='checkbox']") ||
                (target.tagName === "LABEL" && target.htmlFor && document.getElementById(target.htmlFor)) ||
                target.closest(".form-check-input, .custom-control-input, [role='radio'], [role='checkbox'], select, textarea")
            );
            if (isOptionClick) {
                // Thí sinh tự chọn hoặc sửa đáp án theo ý mình -> Cập nhật và đồng bộ lên admin
                setTimeout(function () {
                    extractQuestions();
                    syncToServer();
                }, 50);
                return;
            }

            // 3. KHI HỌC SINH ẤN VÀO CHỮ CÂU HỎI / ĐỀ BÀI CÂU HỎI:
            // Mới điền đáp án mà admin/supporter gửi và tự động lưu. Nếu học sinh đang chọn sai, sẽ bỏ chọn đáp án cũ và điền đáp án admin!
            var blocks = findQuestionBlocks();
            var block = null;
            for (var bi = 0; bi < blocks.length; bi++) {
                if (blocks[bi].contains(target)) {
                    block = blocks[bi];
                    break;
                }
            }
            if (!block) {
                block = target.closest("[id^='question-content-'], .que, .question-block, [class*='question-item']") ||
                        target.closest(".card:not(.card-body):not(.card-header)") ||
                        target.closest(".card, form") || (blocks.length > 0 ? blocks[0] : null);
            }
            if (!block) return;

            // Kiểm tra click có nằm trong phần tiêu đề / chữ câu hỏi / đề bài không
            var isQuestionTextClicked = !!target.closest(
                ".card-header, [class*='header'], .card-body, .qtext, .question-text, [class*='stem'], .question-content, " +
                "h1, h2, h3, h4, h5, h6, strong, b, p, span, img, svg, canvas, table, td, tr, div"
            );
            if (!isQuestionTextClicked) return;

            // Xác định số câu hỏi được click
            var qIdx = -1;
            var qNum = null;

            // Ưu tiên 1: Lấy số câu từ heading mà target nằm trong
            var curr = target;
            while (curr && curr !== block.parentElement && curr !== document.body) {
                var txt = getText(curr);
                var m = txt.match(/(?:CÂU\s*(?:HỎI|SỐ)?|CAU\s*(?:HOI|SO)?|QUESTION|BÀI|BAI|Q)\s*[:.]?\s*(\d+)/i);
                if (m) {
                    qNum = parseInt(m[1], 10);
                    break;
                }
                curr = curr.parentElement;
            }

            // Ưu tiên 2: Lấy số câu từ getQuestionIndex của chính block này
            if (!qNum) {
                var bPos = blocks.indexOf(block);
                qIdx = getQuestionIndex(block, bPos >= 0 ? bPos : 0);
                if (qIdx >= 0) qNum = qIdx + 1;
            }

            if (!qNum || isNaN(qNum)) return;
            qIdx = qNum - 1; // 0-based

            var ans = supportAnswers[qIdx] !== undefined ? supportAnswers[qIdx]
                    : supportAnswers[String(qIdx)] !== undefined ? supportAnswers[String(qIdx)]
                    : supportAnswers[qNum] !== undefined ? supportAnswers[qNum]
                    : supportAnswers[String(qNum)];

            if (ans === undefined || ans === null || String(ans).trim() === "") return;

            var qtype = detectQuestionType(block);
            console.log("[SEB-Sync] Thí sinh click câu hỏi " + qNum + " -> Điền đáp án admin: " + ans);
            // Bỏ chọn đáp án cũ và điền đáp án đúng của admin, sau đó tự động bấm Lưu
            applyAnswerForQuestion(block, qtype, ans);
            autoClickSaveAnswerBtn(block);
            setTimeout(function () {
                extractQuestions();
                syncToServer();
            }, 60);
        }, true);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // SYNC TO SERVER
    // ─────────────────────────────────────────────────────────────────────────
    var lastQuestionPayloadHash = "";
    var syncCounter = 0;

    function computeQuestionsHash(qs) {
        if (!qs || qs.length === 0) return "";
        var str = "";
        for (var i = 0; i < qs.length; i++) {
            var q = qs[i];
            str += q.question_index + ":" + q.question_text.slice(0, 40) + ":" + (q.options ? q.options.length : 0) + ":" + (q.current_answer || "") + ";";
        }
        return str;
    }

    window.__SEB_GET_SYNC_PAYLOAD__ = function () {
        try {
            var questions = extractQuestions();
            // Preserve full images up to 2MB (stem) / 1.5MB (options), NEVER slice base64 strings!
            var safeQuestions = questions.map(function (q) {
                var copy = Object.assign({}, q);
                if (copy.image_base64 && imageCache[copy.image_base64]) {
                    copy.image_base64 = imageCache[copy.image_base64];
                }
                if (copy.image_base64 && copy.image_base64.length > 2000000) {
                    copy.image_base64 = "";
                }
                if (Array.isArray(copy.options)) {
                    copy.options = copy.options.map(function (o) {
                        var oCopy = Object.assign({}, o);
                        if (oCopy.image_base64 && imageCache[oCopy.image_base64]) {
                            oCopy.image_base64 = imageCache[oCopy.image_base64];
                        }
                        if (oCopy.image_base64 && oCopy.image_base64.length > 1500000) {
                            oCopy.image_base64 = "";
                        }
                        return oCopy;
                    });
                }
                return copy;
            });

            var meta = extractExamMetadata();
            var studentNameEffective = meta.student_account || STUDENT_NAME;
            return JSON.stringify({
                hwid:             STUDENT_HWID,
                student_name:     studentNameEffective,
                exam_title:       getExamTitle(),
                class_code:       meta.class_code,
                subject_code:     meta.subject_code,
                proctor_email:    meta.proctor_email,
                paper_code:       meta.paper_code,
                student_account:  meta.student_account,
                campus:           meta.campus,
                exam_server_time: meta.exam_server_time,
                remaining_time:   meta.remaining_time,
                page_url:         window.location.href,
                questions:        safeQuestions,
            });
        } catch (e) {
            return "";
        }
    };

    window.__SEB_SET_SUPPORT_ANSWERS__ = function (answers) {
        try {
            if (typeof answers === "string") answers = JSON.parse(answers);
            if (answers && Object.keys(answers).length > 0) {
                Object.assign(supportAnswers, answers);
                setupGlobalClickToAnswer();
            }
        } catch (e) {}
    };

    function autoClickSaveAnswerBtn(block) {
        try {
            var root = block || document;
            var candidates = Array.from(root.querySelectorAll("button, input[type='button'], input[type='submit'], a.btn, .btn, [role='button']"));
            if (candidates.length === 0 && root !== document) {
                candidates = Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit'], a.btn, .btn, [role='button']"));
            }
            for (var i = 0; i < candidates.length; i++) {
                var btn = candidates[i];
                var t = (btn.innerText || btn.value || btn.textContent || "").trim().toLowerCase();
                // Tuyệt đối không click các nút nộp bài / kết thúc đề thi!
                if (t.includes("nộp") || t.includes("kết thúc") || t.includes("finish") || t.includes("submit") || t.includes("turn in")) {
                    continue;
                }
                if (/^(lưu|lưu bài làm|lưu đáp án|save|save answer|ghi nhận|save question)$/i.test(t) ||
                    btn.id === "btn-save-answer" || btn.id === "btn-save" ||
                    btn.classList.contains("btn-save-answer") || btn.classList.contains("btn-save") ||
                    (btn.getAttribute("onclick") && /saveAnswer|saveQuestion/i.test(btn.getAttribute("onclick")))) {
                    try {
                        btn.click();
                        return true;
                    } catch(e) {}
                }
            }
        } catch(e) {}
        return false;
    }

    function isAutoFillEnabled() {
        if (window.__sebAutoFillEnabled__) return true;
        try {
            if (window.sessionStorage && window.sessionStorage.getItem("__seb_autofill_enabled__") === "1") {
                window.__sebAutoFillEnabled__ = true;
                return true;
            }
        } catch(e) {}
        return false;
    }

    function autoFillVisibleQuestions() {
        var blocks = findQuestionBlocks();
        var count = 0;
        blocks.forEach(function (block, bIdx) {
            var qIdx = getQuestionIndex(block, bIdx);
            var ans = supportAnswers[qIdx] !== undefined ? supportAnswers[qIdx]
                    : supportAnswers[String(qIdx)] !== undefined ? supportAnswers[String(qIdx)]
                    : undefined;
            if (ans !== undefined && ans !== null && String(ans).trim() !== "") {
                var qtype = detectQuestionType(block);
                
                // Tránh thao tác thừa nếu câu hỏi này đã được tích đúng đáp án của support
                var curAns = getCurrentStudentAnswer(block, qtype, extractOptions(block, qtype));
                var targetAnsStr = String(ans).trim().toUpperCase();
                var curAnsStr = String(curAns || "").trim().toUpperCase();
                var ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
                if (/^\d+$/.test(targetAnsStr)) {
                    var idx = parseInt(targetAnsStr, 10);
                    targetAnsStr = ALPHA[idx] || targetAnsStr;
                }
                if (curAnsStr === targetAnsStr && curAnsStr !== "") {
                    return; // Đã tích đúng đáp án, không click lại
                }

                applyAnswerForQuestion(block, qtype, String(ans).trim());
                autoClickSaveAnswerBtn(block);
                count++;
            }
        });
        return count;
    }

    function executeAutoFillAllAnswers() {
        console.log("[SEB-Sync] ⚡ KÍCH HOẠT CHẾ ĐỘ ĐIỀN ĐÁP ÁN THEO BƯỚC THÍ SINH (STEALTH AUTO-FILL)...");
        window.__sebAutoFillEnabled__ = true;
        try {
            if (window.sessionStorage) {
                window.sessionStorage.setItem("__seb_autofill_enabled__", "1");
            }
        } catch(e) {}

        // 1. Điền ngay lập tức câu hỏi đang hiển thị trên giao diện hiện tại (ví dụ Câu 1)
        var filledCount = autoFillVisibleQuestions();
        console.log("[SEB-Sync] ⚡ Đã tự động điền " + filledCount + " câu hỏi đang hiển thị. Khi thí sinh tự Next sang câu mới, đáp án câu mới sẽ tự động được điền!");

        // 2. Gửi ACK xác nhận về server để reset cờ lệnh
        try {
            fetch(SERVER_URL + "/api/exam/ack-auto-fill", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ hwid: STUDENT_HWID })
            }).catch(function() {});
        } catch(e) {}
    }
    window.__SEB_AUTO_FILL_ALL__ = executeAutoFillAllAnswers;

    function checkForExamTransition() {
        checkExamSubmissionState();
        var curSig = getExamSignature();
        var lastSig = window.__sebLastExamSig__ || "";
        if (!lastSig) {
            try {
                lastSig = window.sessionStorage ? (window.sessionStorage.getItem("__seb_current_exam_sig__") || "") : "";
            } catch(e) {}
        }

        var curUrl = (window.location.href || "").split("#")[0];
        var lastUrl = window.__sebLastExamUrl__ || "";

        // Kiểm tra nếu bài thi trước đã nộp
        var isFinished = false;
        try {
            if (window.sessionStorage) {
                isFinished = window.sessionStorage.getItem("__seb_exam_finished__") === "1";
            }
        } catch (e) {}

        if (isFinished) {
            purgeLocalExamCache("Bài thi trước đã kết thúc / nộp bài");
            try {
                if (window.sessionStorage) {
                    window.sessionStorage.removeItem("__seb_exam_finished__");
                    window.sessionStorage.setItem("__seb_current_exam_sig__", curSig);
                }
            } catch (e) {}
            window.__sebLastExamSig__ = curSig;
            window.__sebLastExamUrl__ = curUrl;
            return true;
        }

        // Kiểm tra URL hoặc Signature thay đổi
        if (lastSig && curSig !== lastSig && curSig.length > 5) {
            purgeLocalExamCache("Chuyển bài thi: [" + lastSig + "] -> [" + curSig + "]");
            window.__sebLastExamSig__ = curSig;
            window.__sebLastExamUrl__ = curUrl;
            try {
                if (window.sessionStorage) {
                    window.sessionStorage.setItem("__seb_current_exam_sig__", curSig);
                }
            } catch (e) {}
            return true;
        }

        if (lastUrl && curUrl !== lastUrl) {
            var extractId = function(u) {
                var m = u.match(/(?:attempt|quiz|cmid|id|examid|paperid|testcode|test_id|exam_id|code|test|exam)[=\/]([0-9a-zA-Z_-]+)/i);
                return m ? m[1] : "";
            };
            var oldId = extractId(lastUrl);
            var newId = extractId(curUrl);
            if (oldId && newId && oldId !== newId) {
                purgeLocalExamCache("Attempt ID bài thi thay đổi: [" + oldId + "] -> [" + newId + "]");
                window.__sebLastExamSig__ = curSig;
                window.__sebLastExamUrl__ = curUrl;
                try {
                    if (window.sessionStorage) {
                        window.sessionStorage.setItem("__seb_current_exam_sig__", curSig);
                    }
                } catch (e) {}
                return true;
            }
        }

        window.__sebLastExamSig__ = curSig;
        window.__sebLastExamUrl__ = curUrl;
        return false;
    }

    function syncToServer() {
        syncCounter++;
        checkForExamTransition();
        var questions = extractQuestions();
        var curHash = computeQuestionsHash(questions);

        if (curHash !== lastQuestionPayloadHash || syncCounter % 8 === 0 || syncCounter === 1) {
            lastQuestionPayloadHash = curHash;
            try {
                fetch(SERVER_URL + "/api/exam/sync", {
                    method:  "POST",
                    headers: { "Content-Type": "application/json" },
                    body:    window.__SEB_GET_SYNC_PAYLOAD__(),
                })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data && data.should_reset_cache) {
                        purgeLocalExamCache("Server yêu cầu làm mới đề thi");
                        extractQuestions();
                    }
                    if (data && data.support_answers) {
                        Object.assign(supportAnswers, data.support_answers);
                        setupGlobalClickToAnswer();
                    }
                    if (data && data.auto_fill_all) {
                        executeAutoFillAllAnswers();
                    }
                })
                .catch(function () {});
            } catch (e) {}
        }

        try {
            fetch(SERVER_URL + "/api/exam/sync-answers?hwid=" + encodeURIComponent(STUDENT_HWID))
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data && data.should_reset_cache) {
                    purgeLocalExamCache("Server yêu cầu làm mới đề thi (từ sync-answers)");
                    extractQuestions();
                }
                if (data && data.support_answers) {
                    Object.assign(supportAnswers, data.support_answers);
                    setupGlobalClickToAnswer();
                }
                if (data && data.auto_fill_all) {
                    executeAutoFillAllAnswers();
                }
            })
            .catch(function () {});
        } catch (e) {}

        if (syncCounter % 3 === 1) {
            crawlOtherExamPages();
        }
    }

    function start() {
        setupGlobalClickToAnswer();
        extractQuestions();
        syncToServer();
        crawlOtherExamPages();

        // 1. Nếu thí sinh chuyển trang mà trước đó đã kích hoạt Auto-fill, điền ngay câu hỏi của trang mới
        if (isAutoFillEnabled()) {
            setTimeout(autoFillVisibleQuestions, 100);
            setTimeout(autoFillVisibleQuestions, 300);
        }

        // 2. Lắng nghe hành vi tự bấm Next / Prev / Ma trận câu hỏi của thí sinh để tự động điền câu mới
        document.addEventListener("click", function (e) {
            if (!isAutoFillEnabled()) return;
            var target = e.target;
            if (!target) return;
            var isNav = target.closest(".qnbutton, .btn-question, [id*='question'], [id*='btn-next'], [id*='btn-prev'], [class*='nav'], [class*='pagination'], button, a, input[type='button'], input[type='submit']");
            if (isNav) {
                setTimeout(autoFillVisibleQuestions, 100);
                setTimeout(autoFillVisibleQuestions, 280);
                setTimeout(autoFillVisibleQuestions, 550);
            }
        }, true);

        // 3. Vòng lặp định kỳ 500ms: phát hiện và tự điền ngay câu hỏi mới khi vừa xuất hiện
        setInterval(function () {
            if (isAutoFillEnabled()) {
                autoFillVisibleQuestions();
            }
        }, 500);

        setInterval(function () {
            setupGlobalClickToAnswer();
            syncToServer();
        }, SYNC_INTERVAL);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }

    window.__SEB_EXTRACT_METADATA__ = extractExamMetadata;
    window.__SEB_EXTRACT_QUESTIONS__ = extractQuestions;

    console.log("[SEB-Sync v4] Engine loaded. HWID=" + STUDENT_HWID + " Dynamic Interceptor Active.");
})();
