/**
 * SEB System - Universal Theme & Appearance Engine
 * Supports:
 * - 6 Color Accents (Violet, Ocean Blue, Emerald, Amber Gold, Crimson Red, Cyber Cyan)
 * - 3 Display Modes (Dark Glass, OLED Pure Black, Modern Light)
 * - 5 Premium Vietnamese Fonts (Plus Jakarta Sans, Be Vietnam Pro, Inter, Lexend, Roboto)
 * - 3 Font Scale Presets (Compact 90%, Normal 100%, Large 115%)
 * - Auto-persistence in localStorage
 */

(function () {
    const THEME_STORAGE_KEY = "seb_ui_theme_prefs_v2";

    const ACCENTS = {
        violet: {
            name: "Tím Hoàng Gia",
            primary: "#8b5cf6",
            hover: "#7c3aed",
            gradient: "linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%)",
            glow: "0 0 25px -4px rgba(139, 92, 246, 0.4)",
            badgeBg: "rgba(139, 92, 246, 0.18)",
            badgeText: "#c4b5fd",
            badgeBorder: "rgba(139, 92, 246, 0.35)",
            borderFocus: "#8b5cf6",
            accentBgSubtle: "rgba(139, 92, 246, 0.12)"
        },
        blue: {
            name: "Xanh Đại Dương",
            primary: "#3b82f6",
            hover: "#2563eb",
            gradient: "linear-gradient(135deg, #3b82f6 0%, #0ea5e9 100%)",
            glow: "0 0 25px -4px rgba(59, 130, 246, 0.4)",
            badgeBg: "rgba(59, 130, 246, 0.18)",
            badgeText: "#93c5fd",
            badgeBorder: "rgba(59, 130, 246, 0.35)",
            borderFocus: "#3b82f6",
            accentBgSubtle: "rgba(59, 130, 246, 0.12)"
        },
        emerald: {
            name: "Ngọc Lục Bảo",
            primary: "#10b981",
            hover: "#059669",
            gradient: "linear-gradient(135deg, #10b981 0%, #14b8a6 100%)",
            glow: "0 0 25px -4px rgba(16, 185, 129, 0.4)",
            badgeBg: "rgba(16, 185, 129, 0.18)",
            badgeText: "#6ee7b7",
            badgeBorder: "rgba(16, 185, 129, 0.35)",
            borderFocus: "#10b981",
            accentBgSubtle: "rgba(16, 185, 129, 0.12)"
        },
        amber: {
            name: "Hổ Phách Hoàng Kim",
            primary: "#f59e0b",
            hover: "#d97706",
            gradient: "linear-gradient(135deg, #f59e0b 0%, #ea580c 100%)",
            glow: "0 0 25px -4px rgba(245, 158, 11, 0.4)",
            badgeBg: "rgba(245, 158, 11, 0.18)",
            badgeText: "#fcd34d",
            badgeBorder: "rgba(245, 158, 11, 0.35)",
            borderFocus: "#f59e0b",
            accentBgSubtle: "rgba(245, 158, 11, 0.12)"
        },
        crimson: {
            name: "Đỏ Ruby Cyber",
            primary: "#f43f5e",
            hover: "#e11d48",
            gradient: "linear-gradient(135deg, #f43f5e 0%, #dc2626 100%)",
            glow: "0 0 25px -4px rgba(244, 63, 94, 0.4)",
            badgeBg: "rgba(244, 63, 94, 0.18)",
            badgeText: "#fda4af",
            badgeBorder: "rgba(244, 63, 94, 0.35)",
            borderFocus: "#f43f5e",
            accentBgSubtle: "rgba(244, 63, 94, 0.12)"
        },
        cyan: {
            name: "Neon Cyan (Băng Tuyết)",
            primary: "#06b6d4",
            hover: "#0891b2",
            gradient: "linear-gradient(135deg, #06b6d4 0%, #2563eb 100%)",
            glow: "0 0 25px -4px rgba(6, 182, 212, 0.4)",
            badgeBg: "rgba(6, 182, 212, 0.18)",
            badgeText: "#67e8f9",
            badgeBorder: "rgba(6, 182, 212, 0.35)",
            borderFocus: "#06b6d4",
            accentBgSubtle: "rgba(6, 182, 212, 0.12)"
        }
    };

    const FONTS = {
        jakarta: { name: "Plus Jakarta Sans", css: "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif" },
        vietnam: { name: "Be Vietnam Pro", css: "'Be Vietnam Pro', system-ui, -apple-system, sans-serif" },
        inter:   { name: "Inter (Silicon Valley)", css: "'Inter', system-ui, -apple-system, sans-serif" },
        lexend:  { name: "Lexend (Dịu mắt, đọc nhanh)", css: "'Lexend', system-ui, -apple-system, sans-serif" },
        roboto:  { name: "Roboto (Kinh điển)", css: "'Roboto', system-ui, -apple-system, sans-serif" }
    };

    const MODES = {
        light: { name: "Modern Light (Sáng dịu mắt - Viper)", bg: "#f8fafc", text: "#0f172a" },
        dark:  { name: "Dark Glass (Kính tối)", bg: "#090d16", text: "#f1f5f9" },
        oled:  { name: "Midnight OLED (Đen tuyền)", bg: "#000000", text: "#ffffff" }
    };

    const SCALES = {
        compact: { name: "Nhỏ gọn (90%)", val: "90%" },
        normal:  { name: "Tiêu chuẩn (100%)", val: "100%" },
        large:   { name: "Rộng rãi (112%)", val: "112%" }
    };

    const DEFAULT_PREFS = {
        accent: "emerald",
        mode: "light",
        font: "vietnam",
        scale: "normal"
    };

    function loadPrefs() {
        try {
            const raw = localStorage.getItem(THEME_STORAGE_KEY);
            if (raw) {
                const parsed = JSON.parse(raw);
                return Object.assign({}, DEFAULT_PREFS, parsed);
            }
        } catch (e) {}
        return Object.assign({}, DEFAULT_PREFS);
    }

    function savePrefs(p) {
        try {
            localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(p));
        } catch (e) {}
    }

    let currentPrefs = loadPrefs();

    function applyTheme(prefs) {
        const root = document.documentElement;
        const ac = ACCENTS[prefs.accent] || ACCENTS.emerald;
        const fn = FONTS[prefs.font] || FONTS.vietnam;
        const md = prefs.mode || "light";
        const sc = SCALES[prefs.scale] || SCALES.normal;

        // Apply CSS custom variables
        root.style.setProperty("--primary-accent", ac.primary);
        root.style.setProperty("--primary-hover", ac.hover);
        root.style.setProperty("--primary-gradient", ac.gradient);
        root.style.setProperty("--primary-glow", ac.glow);
        root.style.setProperty("--primary-badge-bg", ac.badgeBg);
        root.style.setProperty("--primary-badge-text", ac.badgeText);
        root.style.setProperty("--primary-badge-border", ac.badgeBorder);
        root.style.setProperty("--primary-accent-subtle", ac.accentBgSubtle);
        root.style.setProperty("--app-font-family", fn.css);
        root.style.setProperty("--app-font-size", sc.val);

        // Inject / Update dynamic style tag in document.head
        let styleTag = document.getElementById("seb-theme-dynamic-styles");
        if (!styleTag) {
            styleTag = document.createElement("style");
            styleTag.id = "seb-theme-dynamic-styles";
            (document.head || root).appendChild(styleTag);
        }
        styleTag.innerHTML = `
            :root {
                --primary-accent: ${ac.primary} !important;
                --primary-hover: ${ac.hover} !important;
                --primary-gradient: ${ac.gradient} !important;
                --primary-glow: ${ac.glow} !important;
                --primary-badge-bg: ${ac.badgeBg} !important;
                --primary-badge-text: ${ac.badgeText} !important;
                --primary-badge-border: ${ac.badgeBorder} !important;
                --primary-accent-subtle: ${ac.accentBgSubtle} !important;
                --app-font-family: ${fn.css} !important;
                --app-font-size: ${sc.val} !important;
            }
            body {
                font-family: ${fn.css} !important;
                font-size: ${sc.val} !important;
            }
            .tab-active-pill, .btn-primary, [data-theme-primary], #header-btn-create-key {
                background: ${ac.gradient} !important;
                color: #ffffff !important;
                box-shadow: 0 4px 18px -2px ${ac.primary}66 !important;
            }
            .theme-accent-color, [data-theme-color] {
                color: ${ac.primary} !important;
            }
            .theme-accent-border, [data-theme-border] {
                border-color: ${ac.primary} !important;
            }
            .theme-badge-style {
                background: ${ac.badgeBg} !important;
                color: ${ac.badgeText} !important;
                border-color: ${ac.badgeBorder} !important;
            }
            /* Override hardcoded purple classes to follow accent */
            .bg-purple-600 {
                background-color: ${ac.primary} !important;
            }
            .hover\\:bg-purple-500:hover {
                background-color: ${ac.hover} !important;
            }
            .text-purple-400, .text-purple-300 {
                color: ${ac.badgeText} !important;
            }
            .border-purple-500, .border-purple-500\\/30, .border-purple-500\\/40, .border-purple-700\\/60 {
                border-color: ${ac.badgeBorder} !important;
            }
            .bg-purple-500\\/20, .bg-purple-500\\/15, .bg-purple-600\\/20, .bg-purple-950\\/80 {
                background-color: ${ac.badgeBg} !important;
            }
            ::-webkit-scrollbar-thumb {
                background: ${ac.primary}66 !important;
            }
            ::-webkit-scrollbar-thumb:hover {
                background: ${ac.primary} !important;
            }
        `;

        // Apply mode class immediately to root (document.documentElement)
        root.classList.remove("theme-mode-dark", "theme-mode-oled", "theme-mode-light", "dark", "light");
        if (md === "light") {
            root.classList.add("theme-mode-light", "light");
        } else if (md === "oled") {
            root.classList.add("theme-mode-oled", "dark");
        } else {
            root.classList.add("theme-mode-dark", "dark");
        }

        // Apply to body if available
        if (document.body) {
            document.body.style.fontFamily = fn.css;
            document.body.style.fontSize = sc.val;

            if (md === "light") {
                document.body.classList.remove("bg-slate-950", "text-slate-100", "bg-black");
                document.body.classList.add("bg-slate-50", "text-slate-900");
            } else if (md === "oled") {
                document.body.classList.remove("bg-slate-50", "text-slate-900", "bg-slate-950");
                document.body.classList.add("bg-black", "text-white");
            } else {
                document.body.classList.remove("bg-slate-50", "text-slate-900", "bg-black");
                document.body.classList.add("bg-slate-950", "text-slate-100");
            }

            document.querySelectorAll("[data-theme-bg]").forEach(el => {
                el.style.background = ac.gradient;
            });
            document.querySelectorAll("[data-theme-color]").forEach(el => {
                el.style.color = ac.primary;
            });

            // Sync Viper theme toggle buttons if present on page
            const iconViperTheme = document.getElementById("icon-viper-theme");
            const textViperTheme = document.getElementById("text-viper-theme");
            if (iconViperTheme && textViperTheme) {
                if (md === "light") {
                    iconViperTheme.className = "fa-solid fa-moon text-indigo-500";
                    textViperTheme.innerText = "Chuyển Chế Độ Tối";
                } else {
                    iconViperTheme.className = "fa-solid fa-sun text-amber-500";
                    textViperTheme.innerText = "Giao diện Viper (Trắng)";
                }
            }
        }
    }

    // Apply on earliest script execution
    try {
        applyTheme(currentPrefs);
    } catch(e) {
        console.warn("Initial applyTheme deferred:", e);
    }

    // Build the Appearance Modal
    function injectAppearanceModal() {
        if (document.getElementById("seb-appearance-modal")) return;

        const modal = document.createElement("div");
        modal.id = "seb-appearance-modal";
        modal.className = "fixed inset-0 z-[9999] hidden flex items-center justify-center p-4 bg-black/75 backdrop-blur-md transition-opacity duration-300 opacity-0 pointer-events-none";
        modal.innerHTML = `
            <div id="seb-appearance-modal-content" class="bg-slate-900 border border-slate-700/80 rounded-3xl max-w-xl w-full p-6 shadow-2xl text-slate-100 space-y-6 transform scale-95 transition-transform duration-300 max-h-[92vh] overflow-y-auto">
                <!-- Modal Header -->
                <div class="flex items-center justify-between pb-4 border-b border-slate-800">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-2xl flex items-center justify-center text-white shadow-lg" style="background: var(--primary-gradient)">
                            <i class="fa-solid fa-palette text-lg"></i>
                        </div>
                        <div>
                            <h2 class="text-base font-extrabold text-white flex items-center gap-2">
                                Tùy Biến Giao Diện & Màu Sắc
                                <span class="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase" style="background: var(--primary-badge-bg); color: var(--primary-badge-text); border: 1px solid var(--primary-badge-border)">Live Preview</span>
                            </h2>
                            <p class="text-xs text-slate-400">Chọn bảng màu, chế độ sáng/tối và phông chữ theo sở thích của bạn</p>
                        </div>
                    </div>
                    <button onclick="window.closeAppearanceModal()" class="w-8 h-8 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>

                <!-- 1. Color Accent Selection -->
                <div class="space-y-3">
                    <label class="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                        <i class="fa-solid fa-droplet text-purple-400"></i> Bảng Màu Chủ Đạo (Accent Theme)
                    </label>
                    <div class="grid grid-cols-2 sm:grid-cols-3 gap-2.5" id="seb-accent-options-grid">
                        ${Object.keys(ACCENTS).map(key => {
                            const a = ACCENTS[key];
                            return `
                                <button type="button" onclick="window.setThemeAccent('${key}')" id="accent-btn-${key}" 
                                    class="flex items-center gap-2.5 p-3 rounded-2xl border text-left transition-all duration-200 bg-slate-800/60 hover:bg-slate-800 border-slate-700/80">
                                    <span class="w-5 h-5 rounded-full shrink-0 shadow-md flex items-center justify-center text-[10px] text-white" style="background: ${a.primary}">
                                        <i class="fa-solid fa-check check-icon hidden"></i>
                                    </span>
                                    <div class="min-w-0 flex-1">
                                        <div class="text-xs font-bold text-white truncate">${a.name}</div>
                                    </div>
                                </button>
                            `;
                        }).join("")}
                    </div>
                </div>

                <!-- 2. Display Mode Selection -->
                <div class="space-y-3">
                    <label class="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                        <i class="fa-solid fa-circle-half-stroke text-blue-400"></i> Chế Độ Màn Hình (Theme Mode)
                    </label>
                    <div class="grid grid-cols-3 gap-2.5">
                        <button type="button" onclick="window.setThemeMode('dark')" id="mode-btn-dark"
                            class="p-3 rounded-2xl border text-center transition-all bg-slate-800/60 hover:bg-slate-800 border-slate-700/80 space-y-1">
                            <i class="fa-solid fa-moon text-base text-indigo-400 block mb-1"></i>
                            <div class="text-xs font-bold text-white">Dark Glass</div>
                            <div class="text-[10px] text-slate-400">Kính tối mờ</div>
                        </button>
                        <button type="button" onclick="window.setThemeMode('oled')" id="mode-btn-oled"
                            class="p-3 rounded-2xl border text-center transition-all bg-slate-800/60 hover:bg-slate-800 border-slate-700/80 space-y-1">
                            <i class="fa-solid fa-square text-base text-slate-300 block mb-1"></i>
                            <div class="text-xs font-bold text-white">OLED Black</div>
                            <div class="text-[10px] text-slate-400">Đen tuyệt đối</div>
                        </button>
                        <button type="button" onclick="window.setThemeMode('light')" id="mode-btn-light"
                            class="p-3 rounded-2xl border text-center transition-all bg-slate-800/60 hover:bg-slate-800 border-slate-700/80 space-y-1">
                            <i class="fa-solid fa-sun text-base text-amber-400 block mb-1"></i>
                            <div class="text-xs font-bold text-white">Modern Light</div>
                            <div class="text-[10px] text-slate-400">Sáng ban ngày</div>
                        </button>
                    </div>
                </div>

                <!-- 3. Typography Selection -->
                <div class="space-y-3">
                    <label class="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                        <i class="fa-solid fa-font text-emerald-400"></i> Phông Chữ Tiếng Việt (Typography)
                    </label>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2" id="seb-font-options-grid">
                        ${Object.keys(FONTS).map(fKey => {
                            const f = FONTS[fKey];
                            return `
                                <button type="button" onclick="window.setThemeFont('${fKey}')" id="font-btn-${fKey}"
                                    class="p-3 rounded-2xl border text-left transition-all bg-slate-800/60 hover:bg-slate-800 border-slate-700/80 flex items-center justify-between"
                                    style="font-family: ${f.css}">
                                    <div>
                                        <div class="text-xs font-bold text-white">${f.name}</div>
                                        <div class="text-[11px] text-slate-400 mt-0.5">Thí sinh: Nguyễn Văn A • 60 câu</div>
                                    </div>
                                    <i class="fa-solid fa-check check-icon text-xs hidden ml-2" style="color: var(--primary-accent)"></i>
                                </button>
                            `;
                        }).join("")}
                    </div>
                </div>

                <!-- 4. Font Scale Selection -->
                <div class="space-y-3">
                    <label class="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                        <i class="fa-solid fa-text-height text-amber-400"></i> Cỡ Chữ Hiển Thị (Font Scale)
                    </label>
                    <div class="grid grid-cols-3 gap-2.5">
                        <button type="button" onclick="window.setThemeScale('compact')" id="scale-btn-compact"
                            class="p-2.5 rounded-2xl border text-center transition-all bg-slate-800/60 hover:bg-slate-800 border-slate-700/80">
                            <span class="text-xs font-bold text-white block">Compact (90%)</span>
                            <span class="text-[10px] text-slate-400">Nhiều câu/trang</span>
                        </button>
                        <button type="button" onclick="window.setThemeScale('normal')" id="scale-btn-normal"
                            class="p-2.5 rounded-2xl border text-center transition-all bg-slate-800/60 hover:bg-slate-800 border-slate-700/80">
                            <span class="text-xs font-bold text-white block">Chuẩn (100%)</span>
                            <span class="text-[10px] text-slate-400">Cân đối tự nhiên</span>
                        </button>
                        <button type="button" onclick="window.setThemeScale('large')" id="scale-btn-large"
                            class="p-2.5 rounded-2xl border text-center transition-all bg-slate-800/60 hover:bg-slate-800 border-slate-700/80">
                            <span class="text-xs font-bold text-white block">To Rõ (112%)</span>
                            <span class="text-[10px] text-slate-400">Dễ nhìn từ xa</span>
                        </button>
                    </div>
                </div>

                <!-- Modal Footer -->
                <div class="flex items-center justify-between pt-4 border-t border-slate-800">
                    <button type="button" onclick="window.resetThemeDefaults()" class="text-xs text-slate-400 hover:text-white transition flex items-center gap-1.5">
                        <i class="fa-solid fa-rotate-left"></i> Khôi phục mặc định
                    </button>
                    <button type="button" onclick="window.closeAppearanceModal()" class="px-5 py-2 rounded-xl text-xs font-bold text-white transition shadow-lg" style="background: var(--primary-gradient)">
                        Hoàn Tất
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        modal.addEventListener("click", function (e) {
            if (e.target === modal) window.closeAppearanceModal();
        });
    }

    function updateModalActiveStates() {
        // Accents
        Object.keys(ACCENTS).forEach(k => {
            const btn = document.getElementById(`accent-btn-${k}`);
            if (btn) {
                const icon = btn.querySelector(".check-icon");
                if (currentPrefs.accent === k) {
                    btn.classList.add("ring-2", "border-transparent");
                    btn.style.setProperty("--tw-ring-color", ACCENTS[k].primary);
                    btn.style.borderColor = ACCENTS[k].primary;
                    if (icon) icon.classList.remove("hidden");
                } else {
                    btn.classList.remove("ring-2");
                    btn.style.borderColor = "";
                    if (icon) icon.classList.add("hidden");
                }
            }
        });

        // Modes
        ["dark", "oled", "light"].forEach(m => {
            const btn = document.getElementById(`mode-btn-${m}`);
            if (btn) {
                if (currentPrefs.mode === m) {
                    btn.classList.add("ring-2", "border-transparent");
                    btn.style.setProperty("--tw-ring-color", "var(--primary-accent)");
                } else {
                    btn.classList.remove("ring-2", "border-transparent");
                }
            }
        });

        // Fonts
        Object.keys(FONTS).forEach(f => {
            const btn = document.getElementById(`font-btn-${f}`);
            if (btn) {
                const icon = btn.querySelector(".check-icon");
                if (currentPrefs.font === f) {
                    btn.classList.add("ring-2", "border-transparent");
                    btn.style.setProperty("--tw-ring-color", "var(--primary-accent)");
                    if (icon) icon.classList.remove("hidden");
                } else {
                    btn.classList.remove("ring-2", "border-transparent");
                    if (icon) icon.classList.add("hidden");
                }
            }
        });

        // Scales
        ["compact", "normal", "large"].forEach(s => {
            const btn = document.getElementById(`scale-btn-${s}`);
            if (btn) {
                if (currentPrefs.scale === s) {
                    btn.classList.add("ring-2", "border-transparent");
                    btn.style.setProperty("--tw-ring-color", "var(--primary-accent)");
                } else {
                    btn.classList.remove("ring-2", "border-transparent");
                }
            }
        });
    }

    // Public Controller APIs
    window.toggleAppearanceModal = function () {
        injectAppearanceModal();
        const modal = document.getElementById("seb-appearance-modal");
        const content = document.getElementById("seb-appearance-modal-content");
        if (!modal) return;

        updateModalActiveStates();
        modal.classList.remove("hidden", "pointer-events-none");
        setTimeout(() => {
            modal.classList.remove("opacity-0");
            modal.classList.add("opacity-100");
            if (content) content.classList.remove("scale-95");
            if (content) content.classList.add("scale-100");
        }, 10);
    };

    window.closeAppearanceModal = function () {
        const modal = document.getElementById("seb-appearance-modal");
        const content = document.getElementById("seb-appearance-modal-content");
        if (!modal) return;

        modal.classList.remove("opacity-100");
        modal.classList.add("opacity-0");
        if (content) {
            content.classList.remove("scale-100");
            content.classList.add("scale-95");
        }
        setTimeout(() => {
            modal.classList.add("hidden", "pointer-events-none");
        }, 300);
    };

    window.setThemeAccent = function (accentKey) {
        if (!ACCENTS[accentKey]) return;
        currentPrefs.accent = accentKey;
        savePrefs(currentPrefs);
        applyTheme(currentPrefs);
        updateModalActiveStates();
    };

    window.setThemeMode = function (modeKey) {
        if (!MODES[modeKey]) return;
        currentPrefs.mode = modeKey;
        savePrefs(currentPrefs);
        applyTheme(currentPrefs);
        updateModalActiveStates();
    };

    window.setThemeFont = function (fontKey) {
        if (!FONTS[fontKey]) return;
        currentPrefs.font = fontKey;
        savePrefs(currentPrefs);
        applyTheme(currentPrefs);
        updateModalActiveStates();
    };

    window.setThemeScale = function (scaleKey) {
        if (!SCALES[scaleKey]) return;
        currentPrefs.scale = scaleKey;
        savePrefs(currentPrefs);
        applyTheme(currentPrefs);
        updateModalActiveStates();
    };

    window.toggleViperTheme = function () {
        const nextMode = currentPrefs.mode === "light" ? "dark" : "light";
        window.setThemeMode(nextMode);
        if (typeof window.onViperThemeChanged === "function") {
            window.onViperThemeChanged(nextMode);
        }
        return nextMode;
    };

    window.getCurrentThemeMode = function () {
        return currentPrefs.mode || "light";
    };

    // Auto-apply and inject on DOM Ready
    function initThemeOnReady() {
        applyTheme(currentPrefs);
        injectAppearanceModal();
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initThemeOnReady);
    } else {
        initThemeOnReady();
    }
})();
