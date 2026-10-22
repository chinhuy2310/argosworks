// utils.js
var records = [];
var DEPARTMENTS = [];
var RECENT_LIMIT = 50;
var viewMode = "recent"; // "recent" | "all"
var filters = { org: "all", cat: "all", q: "", assignee: "all", status: "all" };

var el = {
  home: document.getElementById("viewHome"),
  dash: document.getElementById("viewDash"),
  form: document.getElementById("viewForm"),
  schedule: document.getElementById("viewSchedule"),
  pim: document.getElementById("viewPim"),
  history: document.getElementById("viewHistory"),
  settings: document.getElementById("viewSettings"),
  chat: document.getElementById("sectionChat"),
  tabHome: document.getElementById("tabBtnHome"),
  tabDash: document.getElementById("tabBtnDash"),
  tabForm: document.getElementById("tabBtnForm"),
  tabSchedule: document.getElementById("tabBtnSchedule"),
  tabPim: document.getElementById("tabBtnPim"),
  tabHistory: document.getElementById("tabBtnHistory"),
  tabSettings: document.getElementById("tabBtnSettings"),
  tabChat: document.getElementById("tabBtnChat"),
  navTabsAdmin: document.getElementById("navTabsAdmin"),
  brand: document.getElementById("brandLogo"),
  deptCards: document.getElementById("deptCards"),
  assigneePanel: document.getElementById("assigneePanel"),
  assigneeBar: document.getElementById("assigneeBar"),
  assigneeTableWrap: document.getElementById("assigneeTableWrap"),
  btnToggleAssigneeView: document.getElementById("btnToggleAssigneeView"),
  assigneeCountBadge: document.getElementById("assigneeCountBadge"),
  assigneeBody: document.getElementById("assigneeTableBody"),
  list: document.getElementById("recordList"),
  empty: document.getElementById("emptyState"),
  orgChips: document.getElementById("orgChips"),
  assigneeFilter: document.getElementById("assigneeFilter"),
  filterRow: document.getElementById("filterRow"),
  catFilter: document.getElementById("catFilter"),
  dashViewMode: document.getElementById("dashViewMode"),
  statusFilter: document.getElementById("statusFilter"),
  btnCreateIssue: document.getElementById("btnCreateIssue"),
  search: document.getElementById("searchInput"),
  toast: document.getElementById("toast"),
  recordsWrap: document.getElementById("recordsWrap"),
  recordsHeader: document.getElementById("recordsHeader"),
  recordsLabel: document.getElementById("recordsLabel"),
  recordsCaption: document.getElementById("recordsCaption"),
  viewToggleBtn: document.getElementById("viewToggleBtn"),
  btnToggleTree: document.getElementById("btnToggleTree"),
  syncBtn: document.getElementById("syncBtn"),
  syncCaption: document.getElementById("syncCaption")
};

var CATEGORIES_BY_DEPT = {};
var selectedFiles = [];
var deptAddOpen = false;
var toastTimer;

var loggedInUser = null;
var loginStage = "identify"; // "identify" | "password"
var pendingAccount = null;   // {name, org, email, exists}

var schedEvents = [];
var schedJiraOngoingItems = [];
var schedViewYear, schedViewMonth;
var schedSelectedDate = null;
var schedEditingId = null;

var pimProducts = [];
var pimSearchDebounce = null;
var pimCategories = ["일반"];
var pimSpecTemplates = { "일반": [] };

function escapeHtml(s){
  if(s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, function(c){
    return ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c];
  });
}

function trapFocus(modalEl) {
  if (!modalEl) return function(){};
  var focusableSelectors = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function handleKeyDown(e) {
    if (e.key !== "Tab" || modalEl.hidden) return;
    var focusable = Array.from(modalEl.querySelectorAll(focusableSelectors)).filter(function(el) {
      return el.offsetWidth > 0 || el.offsetHeight > 0 || el === document.activeElement;
    });
    if (focusable.length === 0) return;
    var firstEl = focusable[0];
    var lastEl = focusable[focusable.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === firstEl) {
        lastEl.focus();
        e.preventDefault();
      }
    } else {
      if (document.activeElement === lastEl) {
        firstEl.focus();
        e.preventDefault();
      }
    }
  }

  document.addEventListener("keydown", handleKeyDown);
  return function releaseFocusTrap() {
    document.removeEventListener("keydown", handleKeyDown);
  };
}
window.trapFocus = trapFocus;

function colorVar(colorIndex){ return "var(--dept-color-" + (((colorIndex - 1) % 6) + 1) + ")"; }

function deptById(id){
  for(var i=0;i<DEPARTMENTS.length;i++){ if(DEPARTMENTS[i].id === id) return DEPARTMENTS[i]; }
  return { id: id, name: id, colorIndex: 1 };
}
function orgLabel(o){ return deptById(o).name; }

function showToast(msg, duration, isError){
  if(!el.toast) el.toast = document.getElementById("toast");
  if(!el.toast) return;
  el.toast.textContent = msg;
  if(isError){
    el.toast.classList.add("toast-error");
  } else {
    el.toast.classList.remove("toast-error");
  }
  el.toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function(){
    if(el.toast){
      el.toast.classList.remove("show");
      el.toast.classList.remove("toast-error");
    }
  }, duration || 3200);
}
