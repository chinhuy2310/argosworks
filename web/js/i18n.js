/**
 * i18n.js - Multi-language support (KO / EN)
 * 한국어 (Korean) & English (영어)
 * Supports dynamic real-time language switching without page reloads.
 */

(function(window) {
  "use strict";

  var TRANSLATIONS = {
    ko: {
      // General / Topbar
      "app.title": "ARGOS WORKS - 업무 인수인계 및 AI 협업 기록 시스템",
      "nav.home": "홈",
      "nav.dash": "대시보드",
      "nav.jira": "업무 등록",
      "nav.schedule": "일정",
      "nav.pim": "제품정보",
      "nav.chat": "업무 비서",
      "nav.history": "업무 이력",
      "nav.settings": "환경설정",
      "nav.main_section": "메인 업무",
      "nav.admin_section": "관리자 전용",
      "nav.toggle_menu": "메뉴 접기/펼치기",
      "nav.theme_toggle": "다크 / 라이트 모드 전환",
      "nav.lang_toggle": "언어 변경 (KO / EN)",
      "nav.theme": "화면 모드",
      "nav.theme_dark": "다크 모드",
      "nav.theme_light": "라이트 모드",
      "nav.lang": "언어",
      "nav.notifications": "알림",
      "auth.account_menu": "계정 및 설정",
      "auth.guest_title": "로그인이 필요합니다",
      "auth.guest_desc": "ArgosWorks 서비스 이용을 위해 로그인하세요",
      "auth.login_start": "로그인 / 시작",
      "auth.logout": "로그아웃",

      // Topbar Page Titles
      "title.home": "홈",
      "title.dash": "대시보드",
      "title.form": "업무 등록",
      "title.schedule": "사내 일정",
      "title.pim": "제품 정보 (PIM)",
      "title.chat": "AI 업무 비서",
      "title.history": "업무 이력 로그",
      "title.settings": "환경설정",

      // Dashboard Categories & Filter Toolbar
      "dept.all": "전체",
      "dept.waiting_count": "대기 {count}건",
      "dept.no_waiting": "대기 없음",
      "dept.add_btn": "+ 카테고리 추가",
      "dept.add_title": "새 업무 카테고리 추가",
      "dept.edit_title": "업무 카테고리 정보 수정",
      "dept.manage_btn": "⚙ 카테고리 관리",
      "dept.manage_done": "✓ 관리 완료",
      "dept.edit_btn": "수정",
      "dept.del_btn": "삭제",
      "dept.name_label": "업무 카테고리명",
      "dept.name_ph": "예: 개발팀 또는 영상 분석 프로젝트",
      "dept.name_hint": "대시보드 카드 및 필터에 표시될 카테고리 명칭입니다.",
      "dept.local_label": "로컬 카드 코드 (Local Prefix)",
      "dept.local_ph": "예: DEV (카드 코드: DEV-1, DEV-2...)",
      "dept.local_hint": "로컬 저장 시 자동 채번될 카드 코드 접두사입니다.",
      "dept.jira_label": "Jira 연동 코드 (Project Key)",
      "dept.jira_ph": "예: ARGOS (Jira 프로젝트 키)",
      "dept.jira_hint": "Jira 이슈와 자동 동기화할 프로젝트 키입니다.",
      "dept.modal_cancel": "취소",
      "dept.modal_submit": "추가",
      "dept.modal_update": "저장",
      "dept.toast_added": '"{name}" 카테고리를 추가했습니다.',
      "dept.toast_updated": '"{name}" 카테고리 정보가 수정되었습니다.',
      "dept.toast_exists": "이미 등록된 카테고리명입니다.",
      "dept.toast_failed": "카테고리 저장에 실패했습니다.",
      "dept.toast_deleted": '"{name}" 카테고리가 삭제되었습니다.',
      "dept.toast_del_confirm": '"{name}" 카테고리를 삭제하시겠습니까?',

      // Toolbar filters
      "filter.all_assignees": "전체 담당자",
      "filter.all_categories": "전체 카테고리",
      "filter.view_tree": "트리 보기",
      "filter.view_assignee": "담당자별 그룹",
      "filter.view_flat": "플랫 보기",
      "filter.status_all": "모든 상태",
      "filter.status_inprog": "진행",
      "filter.status_review": "검토",
      "filter.status_todo": "예정",
      "filter.status_done": "완료",
      "filter.status_delayed": "지연",
      "filter.search_ph": "🔍 이슈 키, 요약 검색...",
      "filter.sync_jira": "↙ Jira 동기화",
      "filter.expand_all": "📂 모두 펼치기",
      "filter.collapse_all": "📁 모두 접기",
      "filter.create_task": "➕ 새 작업 등록",
      "filter.assignee_panel_title": "담당자별 현황",
      "filter.view_table": "상세 표",
      "filter.col_total_assigned": "담당 건수",

      // Home View Search
      "home.search_ph": "사내 업무, 제품 모델명, 일정, 담당자 검색...",
      "home.search_btn": "검색",
      "home.sub": "사내 업무 기록 · 인수인계 · 제품 정보 · 일정 통합 검색",
      "home.brand_desc": "업무 인수인계 및 AI 협업 기록 시스템",

      // Settings Tabs & Sections
      "settings.title": "시스템 및 API 설정",
      "settings.desc": "AI 어시스턴트, 벡터 임베딩, 업무 카테고리, 외부 연동 및 워크스페이스 설정을 주제별로 관리합니다.",
      "settings.pill_ai": "AI 어시스턴트",
      "settings.pill_voyage": "임베딩 AI",
      "settings.pill_jira": "Jira API",
      "settings.pill_vectors": "색인 벡터",
      "settings.tab_integrations": "API 및 외부 연동",
      "settings.tab_categories": "업무 카테고리 / 프로젝트",
      "settings.tab_template": "보고서 서식",
      "settings.tab_security": "보안 & DB 백업",
      "settings.tab_users": "사용자 & 권한 (RBAC)",
      "settings.btn_save": "설정 저장",
      "settings.btn_test": "연결 테스트",

      // Chat & BYOK Model Selector
      "chat.welcome": "무엇이든 물어보세요. 업무 카드 검색, 일정 확인, 업무 관리를 도와드립니다.",
      "chat.model_header": "모델",
      "chat.model_default": "기본",
      "chat.model_edit": "수정",
      "chat.model_add": "다른 모델 / 키 추가...",
      "chat.byok_title_add": "개인 AI 모델 / 키 추가",
      "chat.byok_title_edit": "개인 AI 모델 수정",
      "chat.byok_name_label": "표시 이름 (Display Name)",
      "chat.byok_name_ph": "예: Claude Sonnet 4.6 (Thinking)",
      "chat.byok_provider_label": "제공자",
      "chat.byok_model_label": "모델 ID",
      "chat.byok_key_label": "개인 API 키",
      "chat.byok_key_ph": "API 키를 여기에 붙여넣으세요...",
      "chat.byok_key_hint": "키는 브라우저 로컬에 안전하게 저장됩니다.",
      "chat.byok_base_url_label": "커스텀 Base URL",
      "chat.byok_base_url_opt": "(선택사항)",
      "chat.byok_base_url_ph": "예: http://localhost:11434/v1 또는 비워둠",
      "chat.byok_btn_delete": "모델 삭제",
      "chat.byok_btn_cancel": "취소",
      "chat.byok_btn_save": "저장",
      "chat.byok_confirm_delete": "이 모델 설정을 삭제하시겠습니까?",
      "chat.byok_alert_required": "표시 이름과 모델 ID를 입력해주세요.",

      // Common actions
      "common.close": "닫기",
      "common.server_error": "서버에 연결할 수 없습니다."
    },

    en: {
      // General / Topbar
      "app.title": "ARGOS WORKS - Task Handover & AI Collaboration System",
      "nav.home": "Home",
      "nav.dash": "Dashboard",
      "nav.jira": "Register Task",
      "nav.schedule": "Schedule",
      "nav.pim": "Products",
      "nav.chat": "AI Assistant",
      "nav.history": "Audit Log",
      "nav.settings": "Settings",
      "nav.main_section": "Main Workspace",
      "nav.admin_section": "Admin Area",
      "nav.toggle_menu": "Toggle sidebar menu",
      "nav.theme_toggle": "Toggle light / dark mode",
      "nav.lang_toggle": "Change language (KO / EN)",
      "nav.theme": "Theme",
      "nav.theme_dark": "Dark Mode",
      "nav.theme_light": "Light Mode",
      "nav.lang": "Language",
      "nav.notifications": "Notifications",
      "auth.account_menu": "Account & Settings",
      "auth.guest_title": "Sign in required",
      "auth.guest_desc": "Sign in to access your ArgosWorks workspace",
      "auth.login_start": "Sign In / Start",
      "auth.logout": "Sign Out",

      // Topbar Page Titles
      "title.home": "Home",
      "title.dash": "Dashboard",
      "title.form": "Register Task",
      "title.schedule": "Calendar & Schedule",
      "title.pim": "Product Info (PIM)",
      "title.chat": "AI Assistant",
      "title.history": "Audit Activity Log",
      "title.settings": "System Settings",

      // Dashboard Categories & Filter Toolbar
      "dept.all": "All",
      "dept.waiting_count": "{count} pending",
      "dept.no_waiting": "None pending",
      "dept.add_btn": "+ Add Category",
      "dept.add_title": "Add New Work Category",
      "dept.edit_title": "Edit Work Category",
      "dept.manage_btn": "⚙ Manage Categories",
      "dept.manage_done": "✓ Done Managing",
      "dept.edit_btn": "Edit",
      "dept.del_btn": "Delete",
      "dept.name_label": "Work Category Name",
      "dept.name_ph": "e.g. Development Team or AI Project",
      "dept.name_hint": "Display name shown on cards and filter menus.",
      "dept.local_label": "Local Card Code (Prefix)",
      "dept.local_ph": "e.g. DEV (Cards: DEV-1, DEV-2...)",
      "dept.local_hint": "Prefix used for generating sequential local card codes.",
      "dept.jira_label": "Jira Project Key",
      "dept.jira_ph": "e.g. ARGOS (Jira Project Key)",
      "dept.jira_hint": "Jira project key for automated synchronization.",
      "dept.modal_cancel": "Cancel",
      "dept.modal_submit": "Add",
      "dept.modal_update": "Save",
      "dept.toast_added": 'Category "{name}" added successfully.',
      "dept.toast_updated": 'Category "{name}" updated successfully.',
      "dept.toast_exists": "Category name already exists.",
      "dept.toast_failed": "Failed to save category.",
      "dept.toast_deleted": 'Category "{name}" deleted.',
      "dept.toast_del_confirm": 'Are you sure you want to delete category "{name}"?',

      // Toolbar filters
      "filter.all_assignees": "All Assignees",
      "filter.all_categories": "All Categories",
      "filter.view_tree": "Tree View",
      "filter.view_assignee": "By Assignee",
      "filter.view_flat": "Flat View",
      "filter.status_all": "All Statuses",
      "filter.status_inprog": "In Progress",
      "filter.status_review": "In Review",
      "filter.status_todo": "To Do",
      "filter.status_done": "Done",
      "filter.status_delayed": "Delayed",
      "filter.search_ph": "🔍 Search work card, summary...",
      "filter.sync_jira": "⟳ Sync Jira",
      "filter.expand_all": "📂 Expand All",
      "filter.collapse_all": "📁 Collapse All",
      "filter.create_task": "➕ New Task",
      "filter.assignee_panel_title": "Status by Assignee",
      "filter.view_table": "Detailed Table",
      "filter.col_total_assigned": "Assigned Tasks",

      // Home View Search
      "home.search_ph": "Ask anything (e.g., PoE splitter KC cert, OTA firmware, assigned tasks...)",
      "home.search_btn": "Search",
      "home.sub": "Unified search for work logs, handovers, product info, and calendar",
      "home.brand_desc": "Work Handover & AI Collaboration System",

      // Settings Tabs & Sections
      "settings.title": "System & API Settings",
      "settings.desc": "Configure AI Assistant, Vector Embeddings, Work Categories, Integrations, and Workspace branding.",
      "settings.pill_ai": "AI Assistant",
      "settings.pill_voyage": "Embedding AI",
      "settings.pill_jira": "Jira API",
      "settings.pill_vectors": "Indexed Vectors",
      "settings.tab_integrations": "API & Integrations",
      "settings.tab_categories": "Work Categories / Projects",
      "settings.tab_template": "Report Templates",
      "settings.tab_security": "Security & Backup",
      "settings.tab_users": "Users & Access (RBAC)",
      "settings.btn_save": "Save Settings",
      "settings.btn_test": "Test Connections",

      // Chat & BYOK Model Selector
      "chat.welcome": "Ask anything. I can help you search work cards, check schedules, and manage tasks.",
      "chat.model_header": "Model",
      "chat.model_default": "Default",
      "chat.model_edit": "Edit",
      "chat.model_add": "Add other Model / Key...",
      "chat.byok_title_add": "Add Personal AI Model / Key",
      "chat.byok_title_edit": "Edit Personal AI Model",
      "chat.byok_name_label": "Display Name",
      "chat.byok_name_ph": "e.g. Claude Sonnet 4.6 (Thinking)",
      "chat.byok_provider_label": "Provider",
      "chat.byok_model_label": "Model ID",
      "chat.byok_key_label": "Personal API Key",
      "chat.byok_key_ph": "Paste your API key here...",
      "chat.byok_key_hint": "Key is stored securely on your browser.",
      "chat.byok_base_url_label": "Custom Base URL",
      "chat.byok_base_url_opt": "(Optional)",
      "chat.byok_base_url_ph": "e.g. http://localhost:11434/v1 or leave blank",
      "chat.byok_btn_delete": "Delete Model",
      "chat.byok_btn_cancel": "Cancel",
      "chat.byok_btn_save": "Save",
      "chat.byok_confirm_delete": "Are you sure you want to delete this model configuration?",
      "chat.byok_alert_required": "Please enter Display Name and Model ID.",

      // Common actions
      "common.close": "Close",
      "common.server_error": "Cannot connect to server."
    }
  };

  var currentLang = localStorage.getItem("jarvisLang") || "ko";
  if (!TRANSLATIONS[currentLang]) {
    currentLang = "ko";
  }

  function t(key, params) {
    var dict = TRANSLATIONS[currentLang] || TRANSLATIONS.ko;
    var str = dict[key] || TRANSLATIONS.ko[key] || key;
    if (params && typeof params === "object") {
      Object.keys(params).forEach(function(k) {
        str = str.replace(new RegExp("\\{" + k + "\\}", "g"), params[k]);
      });
    }
    return str;
  }

  function getLang() {
    return currentLang;
  }

  function setLang(lang) {
    if (!TRANSLATIONS[lang]) {
      console.warn("Unsupported language:", lang);
      return;
    }
    currentLang = lang;
    localStorage.setItem("jarvisLang", lang);
    applyI18n();
    window.dispatchEvent(new CustomEvent("langchange", { detail: { lang: lang } }));
  }

  function applyI18n() {
    document.documentElement.setAttribute("lang", currentLang);

    // Update all elements with data-i18n attribute
    document.querySelectorAll("[data-i18n]").forEach(function(el) {
      var key = el.getAttribute("data-i18n");
      var text = t(key);
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
        el.value = text;
      } else {
        el.textContent = text;
      }
    });

    // Update elements with data-i18n-ph (placeholder)
    document.querySelectorAll("[data-i18n-ph]").forEach(function(el) {
      var key = el.getAttribute("data-i18n-ph");
      el.placeholder = t(key);
    });

    // Update elements with data-i18n-title (tooltip / title)
    document.querySelectorAll("[data-i18n-title]").forEach(function(el) {
      var key = el.getAttribute("data-i18n-title");
      el.title = t(key);
      if (el.hasAttribute("aria-label")) {
        el.setAttribute("aria-label", t(key));
      }
    });
  }

  window.i18n = {
    t: t,
    getLang: getLang,
    setLang: setLang,
    apply: applyI18n,
    translations: TRANSLATIONS
  };

  // Run on DOM loaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyI18n);
  } else {
    applyI18n();
  }

})(window);
