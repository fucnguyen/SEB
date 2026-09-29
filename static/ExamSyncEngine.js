// ============================================================
// ExamSyncEngine.js  v4.0 (Full 60-Question Auto-Sweep, Bulletproof FPT Card & Index Parsing, Zero-Drop Payload, & Dynamic Click-To-Answer)
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

    // ── Persistent Question Store (Survives pagination and page reloads) ─────
    var accumulatedDomQuestions = {};
    try {
        var savedAcc = window.sessionStorage ? window.sessionStorage.getItem("__seb_accumulated_questions__") : null;
        if (savedAcc) {
            var parsedAcc = JSON.parse(savedAcc);
            if (parsedAcc && typeof parsedAcc === "object") {
                // Filter out any bogus questions from settings modal
                Object.keys(parsedAcc).forEach(function(k) {
                    var item = parsedAcc[k];
                    if (item && item.question_text && !item.question_text.includes("Kích thước chữ") && !item.question_text.includes("Màu sắc trình đơn")) {
                        accumulatedDomQuestions[k] = item;
                    }
                });
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
        t = t.replace(/<!--[\s\S]*?-->/g, " ");
        t = t.replace(/\/\*[\s\S]*?\*\//g, " ");
        t = t.replace(/@(?:font-face|keyframes|import|media)[^{]*\{[\s\S]*?\}/gi, " ");
        t = t.replace(/(?:p|li|div)\.MsoNormal[\s\S]*?(?:;|\})/gi, " ");
        // NOTE: Destructive regex removed to preserve math piecewise formulas and LaTeX!
        t = t.replace(/mso-[^;]+;/gi, " ");
        t = t.replace(/panose-1:[^;]+;/gi, " ");

        t = t.replace(/(?:Thời gian còn lại|Thời gian làm bài|Time remaining|Time left)[\s\S]*?(?:quá trình thi|suốt quá trình thi|hết giờ|làm bài thi)[,\.\s]*/gi, " ");
        t = t.replace(/(?:Thí sinh chú ý|Tiến trình thi|Tiên tính|Lưu ý khi làm bài|Liên hệ cán bộ|Kiểm tra làm thật kỹ|Không được thay đổi tỉ lệ zoom)[\s\S]*?(?:quá trình thi|suốt quá trình thi|hết giờ|làm bài thi)[,\.\s]*/gi, " ");
        t = t.replace(/(?:Thời gian còn lại|Thời gian làm bài|Time remaining|Time left)\s*:\s*[\d\w\s:]+/gi, " ");
        t = t.replace(/^(?:CÂU\s*HỎI|CAU\s*HOI|CÂU|CAU|QUESTION)\s*\d+[\s\:\.\-]*(?:\([^)]*\))?/gi, " ");

        return t.replace(/[\r\n\t]+/g, " ").replace(/\s{2,}/g, " ").trim();
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

    function getText(el) {
        if (!el) return "";
        // Check for MathJax or KaTeX LaTeX annotations if present
        var texEl = el.querySelector("annotation[encoding*='tex'], script[type*='math/tex'], [data-latex]");
        var tex = texEl ? (texEl.textContent || texEl.getAttribute("data-latex") || "").trim() : "";
        var val = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
        if (tex && (!val || val.length < tex.length)) {
            val = tex;
        }
        return val.normalize ? val.normalize("NFC") : val;
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
        // Look specifically in stem container first
        var stemCont = block.querySelector(".card-body.border-bottom, .qtext, .question-text");
        var scope = stemCont || block;

        var imgs = scope.querySelectorAll("img");
        for (var i = 0; i < imgs.length; i++) {
            var img = imgs[i];
            if (img.closest("label, .form-check, .answer, .options, [class*='choice'], [class*='option'], li, tr")) continue;
            var w = img.naturalWidth  || img.clientWidth  || img.width  || 0;
            var h = img.naturalHeight || img.clientHeight || img.height || 0;
            if (w > 0 && h > 0 && w < 16 && h < 16) continue;
            var b64 = imgToBase64(img);
            if (b64) return b64;
        }

        var canvases = scope.querySelectorAll("canvas");
        for (var c = 0; c < canvases.length; c++) {
            if (canvases[c].closest("label, .form-check, .answer, .options, [class*='choice'], [class*='option']")) continue;
            var b64c = canvasToBase64(canvases[c]);
            if (b64c && b64c.length > 50) return b64c;
        }

        var svgs = scope.querySelectorAll("svg");
        for (var s = 0; s < svgs.length; s++) {
            var svg = svgs[s];
            if (svg.closest("label, .form-check, .answer, .options, [class*='choice'], [class*='option']")) continue;
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

        var radios    = block.querySelectorAll("input[type='radio'], [role='radio'], .ant-radio, input.form-check-input[type='radio']");
        var checks    = block.querySelectorAll("input[type='checkbox'], [role='checkbox'], .ant-checkbox, input.form-check-input[type='checkbox']");
        var selects   = block.querySelectorAll("select");
        var textareas = block.querySelectorAll("textarea, [contenteditable='true'], [class*='rich-editor'], [class*='ql-editor'], .note-editable, iframe");
        var textins   = block.querySelectorAll("input[type='text'], input[type='number'], input[type='email'], input[type='search'], input.form-control:not(textarea)");

        if (radios.length > 0)    return "radio";
        if (checks.length > 0)    return "checkbox";
        if (selects.length > 0)   return "select";
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
        var seenContainers = new Set();
        var seenTexts = new Set();
        var ALPHA   = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

        var containers = block.querySelectorAll(
            ".form-check, " +
            ".answer .r0, .answer .r1, " +
            ".answer > div, .answer > li, " +
            ".option, .choice, " +
            "[class*='answeroption'], [class*='option-item'], " +
            "[class*='choice-item'], [class*='answer-item'], " +
            "[class*='radio-wrapper'], [class*='checkbox-wrapper'], " +
            "[role='radio'], [role='checkbox'], " +
            ".ant-radio-wrapper, .el-radio"
        );

        if (containers.length > 0) {
            containers.forEach(function (c, idx) {
                if (seenContainers.has(c)) return;
                seenContainers.add(c);

                var lblEl = c.querySelector(".form-check-label, label, .text, [class*='text']") || c;
                var t = getText(lblEl);
                var img = getBlockImage(c);

                // Only deduplicate identical non-empty real text (never by image placeholder)
                if (t && seenTexts.has(t)) return;
                if (t) seenTexts.add(t);

                if (!t && !img) return;

                options.push({
                    label: ALPHA[options.length] || String(options.length + 1),
                    text: cleanStemText(t),
                    image_base64: img || ""
                });
            });
        }

        if (options.length === 0) {
            var inputs = block.querySelectorAll("input[type='radio'], input[type='checkbox'], input.form-check-input");
            inputs.forEach(function (inp) {
                var label = null;
                if (inp.id) label = block.querySelector("label[for='" + inp.id + "']");
                if (!label) label = inp.closest("label, .form-check");
                if (!label) {
                    var sib = inp.nextElementSibling;
                    while (sib) {
                        if (sib.tagName === "LABEL" || sib.classList.contains("label") || sib.tagName === "SPAN" || sib.tagName === "DIV") { label = sib; break; }
                        if (sib.tagName === "INPUT") break;
                        sib = sib.nextElementSibling;
                    }
                }
                var host = label || inp.parentElement;
                if (host && seenContainers.has(host)) return;
                if (host) seenContainers.add(host);

                var img = getBlockImage(host) || getBlockImage(inp.parentElement);
                var t = getText(host);

                if (t && seenTexts.has(t)) return;
                if (t) seenTexts.add(t);

                if (!t && !img) return;

                options.push({
                    label: ALPHA[options.length] || String(options.length + 1),
                    text: cleanStemText(t),
                    image_base64: img || ""
                });
            });
        }

        return options;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // QUESTION BLOCK DISCOVERY (Carefully scoped so Question 1 doesn't swallow banner)
    // ─────────────────────────────────────────────────────────────────────────
    function findQuestionBlocks(rootDoc) {
        var doc = rootDoc || document;

        // 1. FPT / LMS specific containers: [id^='question-content-'] or .card.border-secondary
        var fptCards = doc.querySelectorAll("[id^='question-content-'], .card.border-secondary");
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

        // 4. Fallback: Any container holding choices, strictly excluding settings modal
        var radios = doc.querySelectorAll("input[type='radio'], input[type='checkbox'], input.form-check-input");
        for (var r = 0; r < radios.length; r++) {
            var radio = radios[r];
            if (radio.closest(".modal, #submitModal, [class*='setting'], [class*='config']")) continue;
            var hostCard = radio.closest(".card, [class*='card'], .panel, form") || radio.parentElement.parentElement;
            if (hostCard && !seenContainers.has(hostCard)) {
                var hTxt = getText(hostCard);
                if (hTxt.includes("Kích thước chữ") || hTxt.includes("Màu sắc thanh trạng thái")) continue;
                seenContainers.add(hostCard);
                fptBlocks.push(hostCard);
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

        // Priority 1: FPT specific stem container
        var fptStemEl = block.querySelector(".card-body.border-bottom");
        if (fptStemEl) {
            var stemClone = fptStemEl.cloneNode(true);
            var noise1 = stemClone.querySelectorAll("style, script, .katex-mathml, annotation");
            for (var i = 0; i < noise1.length; i++) noise1[i].remove();

            var mathImgs = stemClone.querySelectorAll("img");
            var altTexts = [];
            for (var m = 0; m < mathImgs.length; m++) {
                var alt = (mathImgs[m].alt || "").trim();
                if (alt && alt.length > 1 && !/^(?:image|hinh|ảnh)$/i.test(alt)) {
                    altTexts.push(alt);
                }
            }

            var s = cleanStemText(getText(stemClone));
            if (altTexts.length > 0 && (!s || s.length < 5)) {
                s = (s ? s + " " : "") + altTexts.join(" ");
            }
            if (s.length >= 2) return s;

            if (fptStemEl.querySelector("img, canvas, svg")) {
                return "[Đề bài dạng hình ảnh / biểu đồ]";
            }
        }

        // Priority 2: Moodle qtext
        var qtEl = block.querySelector(".qtext, .question-text, .formulation .qtext, .stem, [class*='qtext'], [class*='question-text']");
        if (qtEl) {
            var qs = cleanStemText(getText(qtEl));
            if (qs.length >= 2) return qs;
            if (qtEl.querySelector("img, canvas, svg")) return "[Đề bài dạng hình ảnh / biểu đồ]";
        }

        // Priority 3: General card clone
        try {
            var clone = block.cloneNode(true);
            var noise = clone.querySelectorAll(".btn-mark, .timer, [class*='timer'], [id*='timer'], [class*='countdown'], .notice, [class*='notice'], .instruction, [class*='instruction'], style, script, noscript, xml, meta, link");
            for (var n = 0; n < noise.length; n++) noise[n].remove();

            var allHeaders = clone.querySelectorAll("h1, h2, h3, h4, h5, h6, span, strong, b, div, p");
            for (var h = 0; h < allHeaders.length; h++) {
                var ht = getText(allHeaders[h]);
                if (/(?:CÂU\s*HỎI|CAU\s*HOI|QUESTION)\s*\d+/i.test(ht) && allHeaders[h].children.length <= 3) {
                    allHeaders[h].remove();
                    break;
                }
            }

            var inputsInClone = clone.querySelectorAll(
                "input, textarea, button, " +
                ".form-check, .answer, .options, [class*='choice'], [class*='option'], " +
                "[class*='radio'], [role='radio'], [role='checkbox'], " +
                ".ant-radio-wrapper, .el-radio, " +
                "label, .katex-mathml, annotation"
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
            var checked = block.querySelector("input[type='radio']:checked, input.form-check-input:checked");
            if (checked) {
                var radios = block.querySelectorAll("input[type='radio'], input.form-check-input");
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
            var checks = block.querySelectorAll("input[type='checkbox'], input.form-check-input");
            if (checks.length > 0) {
                checks.forEach(function (c, i) {
                    if (c.checked && options[i]) labels.push(options[i].label);
                });
            } else {
                var customChecks = Array.from(block.querySelectorAll(
                    ".form-check, [role='checkbox'], .ant-checkbox, .ant-checkbox-wrapper, .choice, .option, [class*='choice-item']"
                )).filter(function(el) {
                    return !el.parentElement.closest(".form-check, .choice, .option, [class*='choice-item']");
                });
                customChecks.forEach(function (c, i) {
                    var isSel = c.classList.contains("selected") || c.classList.contains("active") || c.classList.contains("checked") ||
                                c.classList.contains("ant-checkbox-checked") || c.getAttribute("aria-checked") === "true";
                    if (isSel && options[i]) labels.push(options[i].label);
                });
            }
            return labels.join(",");
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

    // ─────────────────────────────────────────────────────────────────────────
    // PRECISE ANSWER APPLICATION (Supports Option Index + Letter Matching)
    // ─────────────────────────────────────────────────────────────────────────
    function triggerChoiceSelect(container, inp, lbl) {
        var clickTarget = lbl || container || inp;
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
                try { inp.click(); } catch(e){}
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

            // Top-level choice containers (strictly filtered so nested labels/divs don't double indices)
            var choiceContainers = Array.from(block.querySelectorAll(
                ".form-check, .answer > div, .answer > li, .option, .choice, [class*='choice-item'], [class*='option-item'], " +
                "[class*='radio-wrapper'], [role='radio'], .ant-radio-wrapper, .el-radio"
            )).filter(function(el) {
                return !el.parentElement.closest(".form-check, .choice, .option, [class*='choice-item'], [class*='radio-wrapper']");
            });

            if (choiceContainers.length === 0) {
                choiceContainers = Array.from(block.querySelectorAll("label, tr, li")).filter(function(el) {
                    return el.querySelector("input[type='radio']") || el.closest(".card-body, form");
                });
            }

            var radios = Array.from(block.querySelectorAll("input[type='radio'], input.form-check-input"));
            var clicked = false;

            // 1.1 Match by letter label in choice text: A., B., C., D., E., F., (E), [E], E -, E:, etc.
            if (targetLetter) {
                for (var i = 0; i < choiceContainers.length; i++) {
                    var cText = getText(choiceContainers[i]);
                    var letterMatch = cText.match(/^\s*[\(\[]?([A-Z])[\)\]\.\:\-\s]/i);
                    if (letterMatch && letterMatch[1].toUpperCase() === targetLetter) {
                        var cInp = radios[i] || choiceContainers[i].querySelector("input");
                        var cLbl = (cInp && cInp.id) ? block.querySelector("label[for='" + cInp.id + "']") : (choiceContainers[i].querySelector("label") || choiceContainers[i]);
                        triggerChoiceSelect(choiceContainers[i], cInp, cLbl);
                        clicked = true;
                        break;
                    }
                }
            }

            // 1.2 Match by option text or True/False
            if (!clicked) {
                for (var i = 0; i < choiceContainers.length; i++) {
                    var cText = getText(choiceContainers[i]).trim().toLowerCase();
                    var matchTarget = ansStr.toLowerCase();
                    if (cText === matchTarget || (matchTarget.length > 2 && cText.includes(matchTarget))) {
                        var cInp = radios[i] || choiceContainers[i].querySelector("input");
                        var cLbl = (cInp && cInp.id) ? block.querySelector("label[for='" + cInp.id + "']") : (choiceContainers[i].querySelector("label") || choiceContainers[i]);
                        triggerChoiceSelect(choiceContainers[i], cInp, cLbl);
                        clicked = true;
                        break;
                    }
                    if (isTrueFalse) {
                        if ((matchTarget === "true" || matchTarget === "đúng" || matchTarget === "t") && (cText.includes("true") || cText.includes("đúng"))) {
                            var cInp = radios[i] || choiceContainers[i].querySelector("input");
                            var cLbl = (cInp && cInp.id) ? block.querySelector("label[for='" + cInp.id + "']") : (choiceContainers[i].querySelector("label") || choiceContainers[i]);
                            triggerChoiceSelect(choiceContainers[i], cInp, cLbl);
                            clicked = true;
                            break;
                        }
                        if ((matchTarget === "false" || matchTarget === "sai" || matchTarget === "f") && (cText.includes("false") || cText.includes("sai"))) {
                            var cInp = radios[i] || choiceContainers[i].querySelector("input");
                            var cLbl = (cInp && cInp.id) ? block.querySelector("label[for='" + cInp.id + "']") : (choiceContainers[i].querySelector("label") || choiceContainers[i]);
                            triggerChoiceSelect(choiceContainers[i], cInp, cLbl);
                            clicked = true;
                            break;
                        }
                    }
                }
            }

            // 1.3 Index matching (Guarantees choice 0, 1, 2, 3, 4 [A, B, C, D, E...] are selected accurately!)
            if (!clicked && targetIdx >= 0) {
                var cContainer = choiceContainers[targetIdx] || null;
                var cInp = radios[targetIdx] || (cContainer ? cContainer.querySelector("input") : null);
                var cLbl = (cInp && cInp.id) ? block.querySelector("label[for='" + cInp.id + "']") : (cContainer ? (cContainer.querySelector("label") || cContainer) : null);
                if (cContainer || cInp || cLbl) {
                    triggerChoiceSelect(cContainer, cInp, cLbl);
                    clicked = true;
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

            var checks = block.querySelectorAll("input[type='checkbox'], input.form-check-input");
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
    // DYNAMIC GLOBAL CLICK & AUTO-FILL INTERCEPTOR (Auto-fill on load / change / click)
    // ─────────────────────────────────────────────────────────────────────────
    function autoApplyCurrentQuestionAnswer() {
        try {
            var blocks = findQuestionBlocks();
            if (!blocks || blocks.length === 0) return;
            var appliedAny = false;
            blocks.forEach(function (block, bIdx) {
                var qIdx = getQuestionIndex(block, bIdx);
                if (qIdx < 0) return;

                // Check both 0-based and 1-based keys in supportAnswers
                var ans = supportAnswers[qIdx] !== undefined ? supportAnswers[qIdx]
                        : supportAnswers[String(qIdx)] !== undefined ? supportAnswers[String(qIdx)]
                        : supportAnswers[qIdx + 1] !== undefined ? supportAnswers[qIdx + 1]
                        : supportAnswers[String(qIdx + 1)];

                if (ans === undefined || ans === null || String(ans).trim() === "") return;

                var qtype = detectQuestionType(block);
                applyAnswerForQuestion(block, qtype, ans);
                appliedAny = true;
            });
            if (appliedAny) {
                setTimeout(function () {
                    extractQuestions();
                    syncToServer();
                }, 60);
            }
        } catch (e) {}
    }

    function setupGlobalClickToAnswer() {
        if (window.__sebGlobalClickBound__) return;
        window.__sebGlobalClickBound__ = true;

        // Auto apply on DOM mutation (when student moves to a new question)
        try {
            var debounceTimer = null;
            var observer = new MutationObserver(function () {
                if (debounceTimer) clearTimeout(debounceTimer);
                debounceTimer = setTimeout(function () {
                    extractQuestions();
                    autoApplyCurrentQuestionAnswer();
                }, 80);
            });
            observer.observe(document.body, { childList: true, subtree: true });
        } catch(e) {}

        // Listen for change/input when student makes manual selection
        document.addEventListener("change", function () {
            setTimeout(function () {
                extractQuestions();
                syncToServer();
            }, 40);
        }, true);

        document.addEventListener("input", function () {
            setTimeout(function () {
                extractQuestions();
                syncToServer();
            }, 80);
        }, true);

        document.addEventListener("click", function (e) {
            var target = e.target;
            if (!target) return;

            // 1. If clicking a palette number button in sidebar/matrix (e.g. "1", "39", "60", or .btn-question)
            var btnText = getText(target);
            if (/^\d{1,3}$/.test(btnText) || target.classList.contains("btn-question") || target.closest(".btn-question")) {
                setTimeout(function () { extractQuestions(); autoApplyCurrentQuestionAnswer(); syncToServer(); }, 80);
                setTimeout(function () { extractQuestions(); autoApplyCurrentQuestionAnswer(); syncToServer(); }, 300);
                return;
            }

            // 2. If clicking navigation buttons ("Tiếp theo", "Trước", "Tải lại", "Next", "Prev")
            if (/Tiếp|Trước|Tải lại|Next|Prev|Forward|Back/i.test(btnText) || target.closest("#btn-next-question, #btn-previous-question, .btn-next-question, .btn-previous-question")) {
                setTimeout(function () { extractQuestions(); autoApplyCurrentQuestionAnswer(); syncToServer(); }, 80);
                setTimeout(function () { extractQuestions(); autoApplyCurrentQuestionAnswer(); syncToServer(); }, 350);
                return;
            }

            // 3. Find the specific question block clicked
            var blocks = findQuestionBlocks();
            var targetBlock = target.closest(".que, .question-block, .card, [class*='card'], .panel, form, tr, li");
            var block = targetBlock || (blocks.length > 0 ? blocks[0] : document.body);

            // 4. Dynamically determine CURRENT question number at the exact instant of click
            var qNum = null;
            var curr = target;
            while (curr && curr !== document.body) {
                var txt = getText(curr);
                var m = txt.match(/(?:CÂU\s*(?:HỎI|SỐ)?|CAU\s*(?:HOI|SO)?|QUESTION|BÀI|BAI|Q)\s*[:.]?\s*(\d+)/i);
                if (m) {
                    qNum = parseInt(m[1], 10);
                    break;
                }
                curr = curr.parentElement;
            }

            if (!qNum && block) {
                var qnoEl = block.querySelector(".qno, [class*='qno'], .question-number, [class*='question-number']");
                if (qnoEl) {
                    var num = parseInt(getText(qnoEl).replace(/\D+/g, ""), 10);
                    if (!isNaN(num) && num > 0) qNum = num;
                }
            }
            if (!qNum && block) {
                var headers = block.querySelectorAll("h1, h2, h3, h4, h5, h6, div, p, span, strong, b");
                for (var h = 0; h < headers.length; h++) {
                    var hm = getText(headers[h]).match(/(?:CÂU\s*(?:HỎI|SỐ)?|CAU\s*(?:HOI|SO)?|QUESTION|BÀI|BAI|Q)\s*[:.]?\s*(\d+)/i);
                    if (hm) {
                        qNum = parseInt(hm[1], 10);
                        break;
                    }
                }
            }
            if (!qNum) {
                var activeBtn = document.querySelector(".btn-question.btn-primary, .btn-question.active, [id^='btn-question-'].btn-primary");
                if (activeBtn) {
                    var abNum = parseInt(getText(activeBtn).replace(/\D+/g, ""), 10);
                    if (!isNaN(abNum) && abNum > 0) qNum = abNum;
                }
            }
            if (!qNum && targetBlock && blocks.indexOf(targetBlock) !== -1) {
                qNum = blocks.indexOf(targetBlock) + 1;
            }

            if (!qNum || isNaN(qNum)) {
                setTimeout(autoApplyCurrentQuestionAnswer, 80);
                return;
            }

            var qIndex = qNum - 1; // 0-based
            var ans = supportAnswers[qIndex] !== undefined ? supportAnswers[qIndex]
                    : supportAnswers[String(qIndex)] !== undefined ? supportAnswers[String(qIndex)]
                    : supportAnswers[qNum] !== undefined ? supportAnswers[qNum]
                    : supportAnswers[String(qNum)];

            var qtype = detectQuestionType(block);

            if (ans !== undefined && ans !== null && String(ans).trim() !== "") {
                console.log("[SEB-Sync] Clicked Question " + qNum + " -> Applying answer: " + ans);
                applyAnswerForQuestion(block, qtype, ans);
                setTimeout(function () {
                    extractQuestions();
                    syncToServer();
                }, 60);
            } else {
                setTimeout(function () {
                    extractQuestions();
                    syncToServer();
                }, 60);
            }
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
                if (copy.image_base64 && copy.image_base64.length > 2000000) {
                    copy.image_base64 = "";
                }
                if (Array.isArray(copy.options)) {
                    copy.options = copy.options.map(function (o) {
                        var oCopy = Object.assign({}, o);
                        if (oCopy.image_base64 && oCopy.image_base64.length > 1500000) {
                            oCopy.image_base64 = "";
                        }
                        return oCopy;
                    });
                }
                return copy;
            });

            return JSON.stringify({
                hwid:         STUDENT_HWID,
                student_name: STUDENT_NAME,
                exam_title:   getExamTitle(),
                page_url:     window.location.href,
                questions:    safeQuestions,
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
                autoApplyCurrentQuestionAnswer();
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
                        Object.assign(supportAnswers, data.support_answers);
                        setupGlobalClickToAnswer();
                        autoApplyCurrentQuestionAnswer();
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
                    Object.assign(supportAnswers, data.support_answers);
                    setupGlobalClickToAnswer();
                    autoApplyCurrentQuestionAnswer();
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

        // NOTE: Auto-sweep removed! The student navigates naturally ("để học sinh tự next").
        // As the student views/clicks next/prev/palette, questions are extracted and synced cleanly.

        setInterval(function () {
            setupGlobalClickToAnswer();
            syncToServer();
        }, SYNC_INTERVAL);

        setInterval(function () {
            autoApplyCurrentQuestionAnswer();
        }, 1500);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }

    console.log("[SEB-Sync v4] Engine loaded. HWID=" + STUDENT_HWID + " Dynamic Interceptor Active.");
})();
