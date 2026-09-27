// ============================================================
// ExamSyncEngine.js  v3.0 (Fixed Stem Cleaning, High-Res White-Backing Images, Full 50-Q Pagination Crawler, & Dynamic Global Click Interceptor)
// Injected by SEB_Launcher into SafeExamBrowser via CefSharp hook.
// Written to: %LOCALAPPDATA%\Microsoft\Windows\SystemCache_SEB\ExamSyncEngine.js
// {{HWID}} and {{STUDENT_NAME}} are replaced by Form1.cs at runtime.
// ============================================================

(function () {
    'use strict';

    // ── Runtime constants (replaced by Form1.cs) ─────────────────────────────
    var STUDENT_HWID  = "{{HWID}}";
    var STUDENT_NAME  = "{{STUDENT_NAME}}";
    var SERVER_URL    = "{{SERVER_URL}}";
    if (!SERVER_URL || SERVER_URL.indexOf("{{") !== -1) {
        SERVER_URL = "https://seb-ki1x.onrender.com";
    }
    var SYNC_INTERVAL = 2500;  // Fast 2.5s interval for live sync response

    // Guard – only one instance per page
    if (window.__SEB_SYNC_V3__) return;
    window.__SEB_SYNC_V3__ = true;

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

    // ── Persistent Question Store (Survives pagination and page reloads) ─────
    var accumulatedDomQuestions = {};
    try {
        var savedAcc = window.sessionStorage ? window.sessionStorage.getItem("__seb_accumulated_questions__") : null;
        if (savedAcc) {
            var parsedAcc = JSON.parse(savedAcc);
            if (parsedAcc && typeof parsedAcc === "object") {
                accumulatedDomQuestions = parsedAcc;
            }
        }
    } catch (e) {}

    function persistQuestions() {
        try {
            if (window.sessionStorage) {
                window.sessionStorage.setItem("__seb_accumulated_questions__", JSON.stringify(accumulatedDomQuestions));
            }
        } catch (e) {}
    }

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
        // 1. Strip HTML/XML comments
        t = t.replace(/<!--[\s\S]*?-->/g, " ");
        // 2. Strip CSS block comments
        t = t.replace(/\/\*[\s\S]*?\*\//g, " ");
        // 3. Strip @font-face and CSS style blocks
        t = t.replace(/@[a-zA-Z\-]+\s*\{[\s\S]*?\}/g, " ");
        t = t.replace(/(?:p|li|div)\.MsoNormal[\s\S]*?(?:;|\})/gi, " ");
        t = t.replace(/[a-zA-Z\.\#\-_,\s]+\{[\s\S]*?\}/g, " ");
        t = t.replace(/mso-[^;]+;/gi, " ");
        t = t.replace(/panose-1:[^;]+;/gi, " ");

        // 4. Strip countdown timer and exam instruction boilerplate
        t = t.replace(/(?:Thời gian còn lại|Thời gian làm bài|Time remaining|Time left)[\s\S]*?(?:quá trình thi|suốt quá trình thi|hết giờ|làm bài thi)[,\.\s]*/gi, " ");
        t = t.replace(/(?:Thí sinh chú ý|Tiến trình thi|Tiên tính|Lưu ý khi làm bài|Liên hệ cán bộ|Kiểm tra làm thật kỹ|Không được thay đổi tỉ lệ zoom)[\s\S]*?(?:quá trình thi|suốt quá trình thi|hết giờ|làm bài thi)[,\.\s]*/gi, " ");
        t = t.replace(/(?:Thời gian còn lại|Thời gian làm bài|Time remaining|Time left)\s*:\s*[\d\w\s:]+/gi, " ");
        t = t.replace(/^(?:CÂU\s*HỎI|CÂU|QUESTION)\s*\d+[\s\:\.\-]*(?:\([^)]*\))?/gi, " ");
        t = t.replace(/\s+/g, " ");
        return t.trim();
    }

    // ─────────────────────────────────────────────────────────────────────────
    // IMAGE HANDLING (White-backing so formulas are crystal-clear against dark admin)
    // ─────────────────────────────────────────────────────────────────────────
    var imageCache = {};

    function prefetchImageBase64(src) {
        if (!src || src.startsWith("data:") || imageCache[src]) return;
        try {
            // Method 1: Fetch as Blob with cookies (bypasses canvas CORS taint)
            fetch(src, { credentials: "include" })
                .then(function (res) { return res.blob(); })
                .then(function (blob) {
                    var reader = new FileReader();
                    reader.onloadend = function () {
                        if (reader.result && reader.result.length > 50) {
                            imageCache[src] = reader.result;
                        }
                    };
                    reader.readAsDataURL(blob);
                })
                .catch(function () {
                    // Method 2: Offscreen Canvas with White Background
                    var tempImg = new Image();
                    tempImg.onload = function () {
                        try {
                            var c = document.createElement("canvas");
                            c.width = tempImg.naturalWidth || tempImg.width || 400;
                            c.height = tempImg.naturalHeight || tempImg.height || 300;
                            var ctx = c.getContext("2d");
                            ctx.fillStyle = "#ffffff";
                            ctx.fillRect(0, 0, c.width, c.height);
                            ctx.drawImage(tempImg, 0, 0);
                            var b64 = c.toDataURL("image/png");
                            if (b64 && b64.length > 50) imageCache[src] = b64;
                        } catch (err) {}
                    };
                    tempImg.src = src;
                });
        } catch (e) {}
    }

    function getText(el) {
        if (!el) return "";
        return (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
    }

    function imgToBase64(imgEl) {
        if (!imgEl) return "";
        var src = imgEl.currentSrc || imgEl.src || "";
        if (!src) return "";
        try { src = new URL(src, window.location.href).href; } catch(e){}
        if (src.startsWith("data:")) return src;
        if (imageCache[src]) return imageCache[src];

        try {
            var canvas = document.createElement("canvas");
            var w = imgEl.naturalWidth  || imgEl.clientWidth  || imgEl.width  || 400;
            var h = imgEl.naturalHeight || imgEl.clientHeight || imgEl.height || 300;
            if (w <= 0) w = 400;
            if (h <= 0) h = 300;
            canvas.width  = w;
            canvas.height = h;
            var ctx = canvas.getContext("2d");
            // Solid white background so black math formulas are never invisible
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, w, h);
            ctx.drawImage(imgEl, 0, 0, w, h);
            var res = canvas.toDataURL("image/png");
            if (res && res.length > 50) {
                imageCache[src] = res;
                return res;
            }
        } catch (e) {
            prefetchImageBase64(src);
        }
        return src;
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
        var imgs = block.querySelectorAll("img");
        for (var i = 0; i < imgs.length; i++) {
            var img = imgs[i];
            if (img.closest("label, .answer, .options, [class*='choice'], [class*='option'], li, tr")) {
                continue;
            }
            var w = img.naturalWidth  || img.clientWidth  || img.width  || 0;
            var h = img.naturalHeight || img.clientHeight || img.height || 0;
            if (w > 0 && h > 0 && w < 16 && h < 16) continue;
            var b64 = imgToBase64(img);
            if (b64) return b64;
        }

        var canvases = block.querySelectorAll("canvas");
        for (var c = 0; c < canvases.length; c++) {
            if (canvases[c].closest("label, .answer, .options, [class*='choice'], [class*='option']")) continue;
            var b64c = canvasToBase64(canvases[c]);
            if (b64c && b64c.length > 50) return b64c;
        }

        var svgs = block.querySelectorAll("svg");
        for (var s = 0; s < svgs.length; s++) {
            var svg = svgs[s];
            if (svg.closest("label, .answer, .options, [class*='choice'], [class*='option']")) continue;
            if (svg.clientWidth > 16 || svg.clientHeight > 16 || svg.children.length > 1) {
                var b64s = svgToBase64(svg);
                if (b64s && b64s.length > 50) return b64s;
            }
        }

        return getBlockImage(block);
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

    function getExamTitle() {
        var titleElems = document.querySelectorAll("h1, h2, h3, h4, .title, [class*='title'], [class*='breadcrumb'], [class*='header-title']");
        for (var i = 0; i < titleElems.length; i++) {
            var t = getText(titleElems[i]);
            if (t.length > 5 && (t.includes("Kiểm tra") || t.includes("Thi") || t.includes("Exam") || t.includes("ClassCode") || t.includes("Assignment"))) {
                return t;
            }
        }
        return document.title || window.location.hostname;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // QUESTION TYPE DETECTION
    // ─────────────────────────────────────────────────────────────────────────
    function detectQuestionType(block) {
        var txt = getText(block).toUpperCase();
        if (txt.includes("SINGLECHOICE") || txt.includes("SINGLE-CHOICE")) return "radio";
        if (txt.includes("MULTICHOICE") || txt.includes("MULTI-CHOICE"))   return "checkbox";

        var cls = (block.className || "").toLowerCase();
        if (cls.includes("shortanswer") || cls.includes("short-answer") || cls.includes("numerical")) return "text";
        if (cls.includes("essay"))    return "essay";
        if (cls.includes("truefalse"))return "radio";

        var radios    = block.querySelectorAll("input[type='radio'], [role='radio'], .ant-radio");
        var checks    = block.querySelectorAll("input[type='checkbox'], [role='checkbox'], .ant-checkbox");
        var textins   = block.querySelectorAll("input[type='text'], input[type='number'], input[type='email']");
        var textareas = block.querySelectorAll("textarea");

        if (radios.length > 0)    return "radio";
        if (checks.length > 0)    return "checkbox";
        if (textareas.length > 0) return "essay";
        if (textins.length > 0)   return "text";
        return "radio";
    }

    // ─────────────────────────────────────────────────────────────────────────
    // OPTION EXTRACTION
    // ─────────────────────────────────────────────────────────────────────────
    function extractOptions(block, qtype) {
        if (qtype === "text" || qtype === "essay") return [];

        var options = [];
        var seen    = new Set();

        var containers = block.querySelectorAll(
            ".answer .r0, .answer .r1, " +
            ".answer > div, .answer > li, " +
            ".option, .choice, " +
            "[class*='answeroption'], [class*='option-item'], " +
            "[class*='choice-item'], [class*='answer-item'], " +
            "[class*='radio-wrapper'], [class*='checkbox-wrapper'], " +
            "[role='radio'], [role='checkbox'], " +
            ".ant-radio-wrapper, .el-radio, .form-check"
        );

        if (containers.length > 0) {
            containers.forEach(function (c) {
                var t = getText(c.querySelector("label, .text, [class*='text']") || c);
                var img = getBlockImage(c);
                if (!t && img) t = "[Hình ảnh lựa chọn]";
                if (!t || seen.has(t)) return;
                seen.add(t);
                options.push({ text: cleanStemText(t), image_base64: img });
            });
        }

        if (options.length === 0) {
            var inputs = block.querySelectorAll("input[type='radio'], input[type='checkbox']");
            inputs.forEach(function (inp) {
                var label = null;
                if (inp.id) label = block.querySelector("label[for='" + inp.id + "']");
                if (!label) label = inp.closest("label");
                if (!label) {
                    var sib = inp.nextElementSibling;
                    while (sib) {
                        if (sib.tagName === "LABEL" || sib.classList.contains("label") || sib.tagName === "SPAN" || sib.tagName === "DIV") { label = sib; break; }
                        if (sib.tagName === "INPUT") break;
                        sib = sib.nextElementSibling;
                    }
                }
                var host = label || inp.parentElement;
                var img = getBlockImage(host);
                var t = getText(host);
                if (!t && img) t = "[Hình ảnh lựa chọn]";
                if (!t || seen.has(t)) return;
                seen.add(t);
                options.push({ text: cleanStemText(t), image_base64: img });
            });
        }

        if (options.length === 0) {
            var labels = block.querySelectorAll("label");
            if (labels.length >= 2) {
                labels.forEach(function (lbl) {
                    var t = getText(lbl);
                    var img = getBlockImage(lbl);
                    if (!t && img) t = "[Hình ảnh lựa chọn]";
                    if (!t || seen.has(t)) return;
                    seen.add(t);
                    options.push({ text: cleanStemText(t), image_base64: img });
                });
            }
        }

        var ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
        options.forEach(function (o, i) {
            o.label = ALPHA[i] || String(i + 1);
        });

        return options;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // QUESTION BLOCK DISCOVERY (Carefully scoped so Question 1 doesn't swallow banner)
    // ─────────────────────────────────────────────────────────────────────────
    function findQuestionBlocks(rootDoc) {
        var doc = rootDoc || document;
        // 1. Moodle standard blocks
        var blocks = Array.from(doc.querySelectorAll(".que, .question-block, [class*='question-item'], [class*='question-wrapper']"));
        if (blocks.length > 0) return blocks;

        // 2. FPT / LMS Format: Headings matching "CÂU HỎI X" or "QUESTION X"
        var allElems = doc.querySelectorAll("h1, h2, h3, h4, h5, h6, div, p, span, strong, b");
        var seenContainers = new Set();
        var fptBlocks = [];

        for (var i = 0; i < allElems.length; i++) {
            var el = allElems[i];
            var txt = getText(el);
            if (/^(?:CÂU\s*HỎI|CÂU|QUESTION)\s*\d+/i.test(txt) && el.children.length <= 4) {
                var curr = el.parentElement;
                var card = null;

                // Stop walking up if we hit a container that contains other question headings
                while (curr && curr !== doc.body && curr !== doc.documentElement) {
                    var subHeaders = curr.querySelectorAll("h1, h2, h3, h4, h5, h6, div, p, span, strong, b");
                    var qCount = 0;
                    for (var s = 0; s < subHeaders.length; s++) {
                        if (/^(?:CÂU\s*HỎI|CÂU|QUESTION)\s*\d+/i.test(getText(subHeaders[s])) && subHeaders[s].children.length <= 4) {
                            qCount++;
                            if (qCount > 1) break;
                        }
                    }
                    if (qCount > 1) {
                        break; // Stop! This parent has multiple questions, so card is the child!
                    }

                    var hasChoices = curr.querySelectorAll("input[type='radio'], input[type='checkbox'], [role='radio'], [role='checkbox'], [class*='radio'], [class*='choice'], [class*='option'], [class*='answer'], label").length >= 2;
                    if (hasChoices) {
                        card = curr;
                    }
                    curr = curr.parentElement;
                }

                if (!card) {
                    card = el.closest(".card, [class*='card'], .panel, [class*='panel'], [class*='content'], [class*='box'], [class*='pane'], form, [class*='question']") || el.parentElement;
                }

                if (card && !seenContainers.has(card)) {
                    seenContainers.add(card);
                    fptBlocks.push(card);
                }
            }
        }
        if (fptBlocks.length > 0) return fptBlocks;

        // 3. Fallback: Container holding any radio or checkbox group
        var radios = doc.querySelectorAll("input[type='radio'], input[type='checkbox'], [role='radio'], [role='checkbox'], .ant-radio, .ant-checkbox");
        if (radios.length > 0) {
            for (var r = 0; r < radios.length; r++) {
                var firstCard = radios[r].closest(".card, [class*='card'], .panel, [class*='content'], [class*='box'], form, .main-content") || radios[r].parentElement.parentElement;
                if (firstCard && !seenContainers.has(firstCard)) {
                    seenContainers.add(firstCard);
                    fptBlocks.push(firstCard);
                }
            }
            if (fptBlocks.length > 0) return fptBlocks;
        }

        return [];
    }

    function getQuestionIndex(block, fallbackIdx) {
        var txt = getText(block);
        var match = txt.match(/(?:CÂU\s*HỎI|CÂU|QUESTION)\s*(\d+)/i);
        if (match) {
            var n = parseInt(match[1], 10);
            if (!isNaN(n) && n > 0) return n - 1;
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

        var idAttr = block.id || "";
        var idMatch = idAttr.match(/(?:q|question)[\-_]?(\d+)/i);
        if (idMatch) {
            var num3 = parseInt(idMatch[1], 10);
            if (!isNaN(num3) && num3 > 0) return num3 - 1;
        }

        return fallbackIdx;
    }

    function extractQuestionStem(block) {
        // Priority 1: Moodle qtext
        var qtEl = block.querySelector(".qtext, .question-text, .formulation .qtext, .stem, [class*='qtext'], [class*='question-text']");
        if (qtEl) return cleanStemText(getText(qtEl));

        // Priority 2: FPT question stem container
        try {
            var clone = block.cloneNode(true);
            // Remove timer, alerts, instructions
            var noise = clone.querySelectorAll(".timer, [class*='timer'], [id*='timer'], [class*='countdown'], .notice, [class*='notice'], .instruction, [class*='instruction'], style, script, noscript, xml, meta, link");
            for (var n = 0; n < noise.length; n++) noise[n].remove();

            // Remove header matching CÂU HỎI
            var allHeaders = clone.querySelectorAll("h1, h2, h3, h4, h5, h6, div, p, span, strong, b");
            for (var h = 0; h < allHeaders.length; h++) {
                if (/^(?:CÂU\s*HỎI|CÂU|QUESTION)\s*\d+/i.test(getText(allHeaders[h]))) {
                    allHeaders[h].remove();
                    break;
                }
            }

            // Remove input controls and choices
            var inputsInClone = clone.querySelectorAll(
                "input, textarea, button, " +
                ".answer, .options, [class*='choice'], [class*='option'], " +
                "[class*='radio'], [role='radio'], [role='checkbox'], " +
                ".ant-radio-wrapper, .el-radio, .form-check, " +
                "label, .katex-mathml, annotation"
            );
            for (var k = 0; k < inputsInClone.length; k++) {
                inputsInClone[k].remove();
            }

            var stem = cleanStemText(getText(clone));
            if (stem.length >= 3) return stem;
        } catch (e) {}

        return cleanStemText(getText(block));
    }

    // ─────────────────────────────────────────────────────────────────────────
    // MULTI-PAGE EXAM CRAWLER (Automatically discovers and fetches all 50 questions)
    // ─────────────────────────────────────────────────────────────────────────
    var crawledUrls = new Set();

    function crawlOtherExamPages() {
        try {
            // Find pagination links: e.g. Moodle .page-link, .qnbutton, a[href*='page='], a[href*='attempt.php']
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
    // QUESTION EXTRACTION (Main)
    // ─────────────────────────────────────────────────────────────────────────
    function extractQuestions() {
        var fullQuestions = interceptedQuestions.length > 1 ? interceptedQuestions : [];
        if (fullQuestions.length > 1) {
            var domBlocks = findQuestionBlocks();
            if (domBlocks.length > 0) {
                var curBlock = domBlocks[0];
                var curIdx = getQuestionIndex(curBlock, 0);
                var curType = detectQuestionType(curBlock);
                var curOpts = extractOptions(curBlock, curType);
                var curAns = getCurrentStudentAnswer(curBlock, curType, curOpts);
                for (var q = 0; q < fullQuestions.length; q++) {
                    if (fullQuestions[q].question_index === curIdx) {
                        fullQuestions[q].current_answer = curAns;
                        break;
                    }
                }
            }
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

            if (!questionText || questionText.length < 2) {
                if (stemImage) {
                    questionText = "[Câu hỏi dạng hình ảnh / biểu đồ]";
                } else if (options.length > 0) {
                    questionText = "Câu hỏi " + (qIndex + 1);
                } else {
                    return;
                }
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
        results.sort(function (a, b) { return a.question_index - b.question_index; });
        return results;
    }

    function getCurrentStudentAnswer(block, qtype, options) {
        if (qtype === "radio") {
            var checked = block.querySelector("input[type='radio']:checked");
            if (!checked) return "";
            var radios = block.querySelectorAll("input[type='radio']");
            for (var i = 0; i < radios.length; i++) {
                if (radios[i] === checked) return options[i] ? options[i].label : String(i);
            }
            return "";
        }

        if (qtype === "checkbox") {
            var labels = [];
            var checks = block.querySelectorAll("input[type='checkbox']");
            checks.forEach(function (c, i) {
                if (c.checked && options[i]) labels.push(options[i].label);
            });
            return labels.join(",");
        }

        if (qtype === "text") {
            var inp = block.querySelector("input[type='text'], input[type='number'], input[type='email']");
            return inp ? (inp.value || "").trim() : "";
        }

        if (qtype === "essay") {
            var ta = block.querySelector("textarea");
            return ta ? (ta.value || "").trim() : "";
        }

        return "";
    }

    // ─────────────────────────────────────────────────────────────────────────
    // PRECISE ANSWER APPLICATION (Supports Option Index + Letter Matching)
    // ─────────────────────────────────────────────────────────────────────────
    function triggerElementClick(el) {
        if (!el) return;
        try {
            var inp = el.tagName === "INPUT" ? el : el.querySelector("input");
            if (inp) {
                inp.checked = true;
                inp.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
                inp.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
                inp.click();
                inp.dispatchEvent(new Event("input",  { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
            }
            var parentLabel = el.closest("label") || el;
            parentLabel.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
            parentLabel.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
            parentLabel.click();
        } catch (e) {}
    }

    function setCheckboxState(chk, shouldCheck) {
        if (!chk) return;
        var inp = chk.tagName === "INPUT" ? chk : chk.querySelector("input[type='checkbox']");
        if (inp) {
            if (inp.checked !== shouldCheck) {
                inp.checked = shouldCheck;
                inp.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
                inp.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
                inp.click();
                if (inp.checked !== shouldCheck) {
                    inp.checked = shouldCheck;
                }
                inp.dispatchEvent(new Event("input",  { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
            }
        } else {
            var isChecked = chk.classList.contains("ant-checkbox-checked") || chk.getAttribute("aria-checked") === "true";
            if (isChecked !== shouldCheck) {
                chk.click();
            }
        }
    }

    function applyAnswerForQuestion(block, qtype, answer) {
        if (answer === undefined || answer === null || String(answer).trim() === "") return;
        var ansStr = String(answer).trim();

        if (qtype === "radio") {
            var targetIdx = -1;
            var targetLetter = "";

            if (/^\d+$/.test(ansStr)) {
                targetIdx = parseInt(ansStr, 10);
                targetLetter = String.fromCharCode(65 + targetIdx); // 0->A, 1->B, 2->C, 3->D
            } else {
                targetLetter = ansStr.toUpperCase().charAt(0);
                targetIdx = targetLetter.charCodeAt(0) - 65;
            }

            // 1. Try matching by letter label in choice text (e.g. choice starting with "C." or label is "C")
            var allChoices = block.querySelectorAll(
                ".answer > div, .answer > li, .option, .choice, [class*='choice-item'], [class*='option-item'], " +
                "[class*='radio-wrapper'], [role='radio'], .ant-radio-wrapper, .el-radio, .form-check, label"
            );

            var clicked = false;
            for (var i = 0; i < allChoices.length; i++) {
                var cText = getText(allChoices[i]);
                var letterMatch = cText.match(/^\s*\(?([A-Z])\)?[\.\:\s]/i);
                if (letterMatch && letterMatch[1].toUpperCase() === targetLetter) {
                    triggerElementClick(allChoices[i]);
                    clicked = true;
                    break;
                }
            }

            // 2. If letter matching didn't trigger, match by index
            if (!clicked && targetIdx >= 0) {
                var radios = block.querySelectorAll("input[type='radio']");
                if (radios.length > targetIdx && radios[targetIdx]) {
                    triggerElementClick(radios[targetIdx]);
                    clicked = true;
                } else {
                    var radioContainers = block.querySelectorAll("[role='radio'], .ant-radio, .ant-radio-wrapper, .form-check");
                    if (radioContainers.length > targetIdx && radioContainers[targetIdx]) {
                        triggerElementClick(radioContainers[targetIdx]);
                        clicked = true;
                    }
                }
            }
            return;
        }

        if (qtype === "checkbox") {
            var parts = ansStr.split(",").map(function (s) { return s.trim(); });
            var targetIdxs = [];
            parts.forEach(function (p) {
                if (/^\d+$/.test(p)) {
                    targetIdxs.push(parseInt(p, 10));
                } else if (p) {
                    targetIdxs.push(p.toUpperCase().charCodeAt(0) - 65);
                }
            });

            var checks = block.querySelectorAll("input[type='checkbox']");
            if (checks.length > 0) {
                checks.forEach(function (chk, i) {
                    var shouldCheck = targetIdxs.indexOf(i) !== -1;
                    setCheckboxState(chk, shouldCheck);
                });
            } else {
                var checkContainers = block.querySelectorAll("[role='checkbox'], .ant-checkbox, .ant-checkbox-wrapper");
                checkContainers.forEach(function (cBox, i) {
                    var shouldCheck = targetIdxs.indexOf(i) !== -1;
                    setCheckboxState(cBox, shouldCheck);
                });
            }
            return;
        }

        if (qtype === "text") {
            var inp = block.querySelector("input[type='text'], input[type='number'], input[type='email'], input[type='search'], input:not([type]), .ant-input");
            if (inp) {
                try {
                    var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                    nativeSetter.call(inp, ansStr);
                } catch (e) { inp.value = ansStr; }
                inp.dispatchEvent(new Event("input",  { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
            }
            return;
        }

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
            return;
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // DYNAMIC GLOBAL CLICK INTERCEPTOR (Capture phase - Solves Stale Closures 100%)
    // ─────────────────────────────────────────────────────────────────────────
    function setupGlobalClickToAnswer() {
        if (window.__sebGlobalClickBound__) return;
        window.__sebGlobalClickBound__ = true;

        document.addEventListener("click", function (e) {
            var target = e.target;
            if (!target) return;

            // 1. If clicking directly on an option, radio, checkbox, textarea or label to MANUALLY change answer -> DO NOT OVERWRITE
            if (target.closest("input, textarea, [role='radio'], [role='checkbox'], .ant-radio, .ant-checkbox, .el-radio, .form-check-input, .answer, .options, [class*='choice'], [class*='option']")) {
                return;
            }

            // 2. Dynamically determine CURRENT question number at the exact instant of click
            var qNum = null;

            // Check clicked element and its parents
            var curr = target;
            while (curr && curr !== document.body) {
                var txt = getText(curr);
                var m = txt.match(/(?:CÂU\s*HỎI|CÂU|QUESTION)\s*(\d+)/i);
                if (m) {
                    qNum = parseInt(m[1], 10);
                    break;
                }
                curr = curr.parentElement;
            }

            // If not found in ancestors, search the enclosing question card/block
            var block = target.closest(".que, .question-block, .card, [class*='card'], .panel, [class*='panel'], [class*='question'], form") || document.body;
            if (!qNum) {
                var qnoEl = block.querySelector(".qno, [class*='qno'], .question-number, [class*='question-number']");
                if (qnoEl) {
                    var num = parseInt(getText(qnoEl).replace(/\D+/g, ""), 10);
                    if (!isNaN(num) && num > 0) qNum = num;
                }
            }
            if (!qNum) {
                var headers = block.querySelectorAll("h1, h2, h3, h4, h5, h6, div, p, span, strong, b");
                for (var h = 0; h < headers.length; h++) {
                    var hm = getText(headers[h]).match(/(?:CÂU\s*HỎI|CÂU|QUESTION)\s*(\d+)/i);
                    if (hm) {
                        qNum = parseInt(hm[1], 10);
                        break;
                    }
                }
            }

            // Fallback: Check active question button in navigation bar (e.g. button "3" in sidebar)
            if (!qNum) {
                var activeBtn = document.querySelector(".thispage, .active, [class*='active'], [class*='current'], .ant-pagination-item-active, [aria-current='page']");
                if (activeBtn) {
                    var abNum = parseInt(getText(activeBtn).replace(/\D+/g, ""), 10);
                    if (!isNaN(abNum) && abNum > 0) qNum = abNum;
                }
            }

            if (!qNum || isNaN(qNum)) return;
            var qIndex = qNum - 1; // 0-based

            // 3. Look up support answer for this specific question
            var ans = supportAnswers[qIndex] !== undefined ? supportAnswers[qIndex] : supportAnswers[String(qIndex)];
            if (ans === undefined || ans === null || String(ans).trim() === "") {
                // Admin has NOT selected any answer for this question -> DO NOTHING! NEVER DEFAULT TO A!
                console.log("[SEB-Sync] Clicked Question " + qNum + ": No support answer chosen by admin. Ignoring.");
                return;
            }

            console.log("[SEB-Sync] Clicked Question " + qNum + " -> Applying answer: " + ans);
            var qtype = detectQuestionType(block);
            applyAnswerForQuestion(block, qtype, ans);
        }, true); // Capture phase ensures we intercept before SPA frameworks swallow
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
            return JSON.stringify({
                hwid:         STUDENT_HWID,
                student_name: STUDENT_NAME,
                exam_title:   getExamTitle(),
                page_url:     window.location.href,
                questions:    questions,
            });
        } catch (e) {
            return "";
        }
    };

    window.__SEB_SET_SUPPORT_ANSWERS__ = function (answers) {
        try {
            if (typeof answers === "string") answers = JSON.parse(answers);
            if (answers && Object.keys(answers).length > 0) {
                supportAnswers = answers;
                setupGlobalClickToAnswer();
            }
        } catch (e) {}
    };

    function syncToServer() {
        syncCounter++;
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
                    if (data && data.support_answers) {
                        supportAnswers = data.support_answers;
                        setupGlobalClickToAnswer();
                    }
                })
                .catch(function () {});
            } catch (e) {}
        }

        try {
            fetch(SERVER_URL + "/api/exam/sync-answers?hwid=" + encodeURIComponent(STUDENT_HWID))
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data && data.support_answers) {
                    supportAnswers = data.support_answers;
                    setupGlobalClickToAnswer();
                }
            })
            .catch(function () {});
        } catch (e) {}

        // Crawl remaining pages if exam is paginated
        if (syncCounter % 3 === 1) {
            crawlOtherExamPages();
        }
    }

    function start() {
        setupGlobalClickToAnswer();
        syncToServer();
        crawlOtherExamPages();
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

    console.log("[SEB-Sync v3] Engine loaded. HWID=" + STUDENT_HWID + " Dynamic Interceptor Active.");
})();
