// notifications.js — ARGOS WORKS Topbar Notification Popover & Alerts
// =========================================================================

(function(){
  var notifBtn = null;
  var notifMenu = null;
  var notifList = null;
  var notifBadge = null;
  var notifPill = null;
  var markAllBtn = null;
  var soundBtn = null;
  var pushBanner = null;
  var enablePushBtn = null;
  var testPushBtn = null;
  var tabBtns = [];

  var allNotifications = [];
  var currentFilter = "all";
  var READ_STORAGE_KEY = "argos_read_notifications_v1";
  var SOUND_STORAGE_KEY = "argos_notif_sound_enabled";

  var notifiedIds = {};
  var isFirstFetch = true;

  function isSoundEnabled(){
    try {
      var val = localStorage.getItem(SOUND_STORAGE_KEY);
      return val === null ? true : val === "true";
    } catch(e) {
      return true;
    }
  }

  function setSoundEnabled(enabled){
    try {
      localStorage.setItem(SOUND_STORAGE_KEY, enabled ? "true" : "false");
    } catch(e) {}
    updateSoundBtn();
  }

  function updateSoundBtn(){
    if(!soundBtn) return;
    var on = isSoundEnabled();
    soundBtn.textContent = on ? "🔊" : "🔇";
    soundBtn.title = on ? "알림음 토글 (켜짐)" : "알림음 토글 (음소거)";
    soundBtn.setAttribute("aria-label", on ? "알림음 켜짐" : "알림음 음소거");
  }

  function playNotifChime(){
    if(!isSoundEnabled()) return;
    try {
      var AudioCtx = window.AudioContext || window.webkitAudioContext;
      if(!AudioCtx) return;
      var ctx = new AudioCtx();
      var now = ctx.currentTime;

      // Tone 1: D5 (587.33 Hz)
      var osc1 = ctx.createOscillator();
      var gain1 = ctx.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(587.33, now);
      gain1.gain.setValueAtTime(0.12, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.25);

      // Tone 2: A5 (880.00 Hz)
      var osc2 = ctx.createOscillator();
      var gain2 = ctx.createGain();
      osc2.type = "sine";
      osc2.frequency.setValueAtTime(880.00, now + 0.12);
      gain2.gain.setValueAtTime(0.14, now + 0.12);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.38);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.12);
      osc2.stop(now + 0.40);
    } catch(e) {}
  }

  function updatePushBanner(){
    if(!pushBanner) return;
    if(!("Notification" in window)){
      pushBanner.hidden = true;
      return;
    }
    if(Notification.permission === "default"){
      pushBanner.hidden = false;
    } else {
      pushBanner.hidden = true;
    }
  }

  function requestPushPermission(){
    if(!("Notification" in window)){
      if(typeof showToast === "function") showToast("현재 브라우저에서는 데스크톱 알림을 지원하지 않습니다.");
      return;
    }
    Notification.requestPermission().then(function(perm){
      updatePushBanner();
      if(perm === "granted"){
        if(typeof showToast === "function") showToast("✅ 데스크톱 실시간 알림이 허용되었습니다.");
        triggerDesktopNotification({
          title: "ARGOS WORKS",
          desc: "데스크톱 실시간 알림이 성공적으로 활성화되었습니다.",
          tag: "연결성공"
        });
        playNotifChime();
      } else if(perm === "denied"){
        if(typeof showToast === "function") showToast("⚠️ 브라우저 주소창에서 알림 권한을 허용할 수 있습니다.");
      }
    });
  }

  function triggerDesktopNotification(item){
    if(!("Notification" in window) || Notification.permission !== "granted") return;
    try {
      var title = item.title || "ARGOS WORKS 알림";
      var body = item.content || item.desc || "";
      if(item.tag) body = "[" + item.tag + "] " + body;

      var n = new Notification(title, {
        body: body,
        icon: "/favicon.svg",
        tag: item.id || ("argos_" + Date.now()),
        renotify: false
      });

      n.onclick = function(){
        window.focus();
        if(item.id) markIdAsRead(item.id);
        n.close();

        var tag = item.tag || "";
        var title = item.title || "";
        if(tag === "가입요청" || tag === "가입승인" || title.indexOf("가입 승인") !== -1 || title.indexOf("계정 발급") !== -1){
          if(typeof showTab === "function") showTab("settings");
          if(typeof switchSettingsTab === "function") switchSettingsTab("users");
          setTimeout(function(){
            var filterStatus = document.getElementById("adminUserFilterStatus");
            if(filterStatus){
              filterStatus.value = "pending";
              if(typeof renderAdminUsersTable === "function") renderAdminUsersTable();
            }
            if(typeof loadAdminUsers === "function") loadAdminUsers();
          }, 100);
          return;
        }

        if(item.record_id){
          if(typeof window.showIssueInCanvas === "function"){
            window.showIssueInCanvas(item.record_id);
          } else if(typeof showTab === "function"){
            showTab("dash");
          }
          return;
        }

        if(typeof showTab === "function"){
          showTab("dash");
        }
      };
    } catch(e){
      console.warn("Failed to trigger desktop notification:", e);
    }
  }

  function getReadIds(){
    try {
      var raw = localStorage.getItem(READ_STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch(e) {
      return [];
    }
  }

  function setReadIds(ids){
    try {
      localStorage.setItem(READ_STORAGE_KEY, JSON.stringify(ids));
    } catch(e) {}
  }

  function markIdAsRead(id){
    if(!id) return;
    var ids = getReadIds();
    if(ids.indexOf(id) === -1){
      ids.push(id);
      setReadIds(ids);
    }
    allNotifications.forEach(function(item){
      if(item.id === id) item.is_read = true;
    });
    updateBadge();
    renderList();
    if(typeof apiPost === "function"){
      apiPost("/api/notifications/read", { id: id }).catch(function(){});
    }
  }

  function markAllAsRead(){
    var ids = getReadIds();
    allNotifications.forEach(function(item){
      item.is_read = true;
      if(ids.indexOf(item.id) === -1){
        ids.push(item.id);
      }
    });
    setReadIds(ids);
    updateBadge();
    renderList();
    if(typeof apiPost === "function"){
      apiPost("/api/notifications/read-all", {}).catch(function(){});
    }
    if(typeof showToast === "function"){
      showToast("모든 알림을 읽음 처리했습니다.");
    }
  }

  function formatRelativeTime(timeStr){
    if(!timeStr) return "";
    try {
      var d = new Date(timeStr.replace(" ", "T"));
      if(isNaN(d.getTime())) return timeStr;
      var now = new Date();
      var diffMs = now.getTime() - d.getTime();
      var diffSec = Math.floor(diffMs / 1000);
      if(diffSec < 60) return "방금 전";
      var diffMin = Math.floor(diffSec / 60);
      if(diffMin < 60) return diffMin + "분 전";
      var diffHour = Math.floor(diffMin / 60);
      if(diffHour < 24) return diffHour + "시간 전";
      var diffDay = Math.floor(diffHour / 24);
      if(diffDay === 1) return "어제";
      if(diffDay < 7) return diffDay + "일 전";
      var mm = String(d.getMonth() + 1).padStart(2, "0");
      var dd = String(d.getDate()).padStart(2, "0");
      return mm + "." + dd;
    } catch(e){
      return timeStr;
    }
  }

  function getIconSvg(type){
    switch(type){
      case "deadline":
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>';
      case "comment":
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';
      case "status":
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>';
      case "jira":
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>';
      case "assign":
      default:
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="23" y1="11" x2="17" y2="11"></line></svg>';
    }
  }

  function isItemUnread(item){
    if(item.is_read) return false;
    var readIds = getReadIds();
    return readIds.indexOf(item.id) === -1;
  }

  function updateBadge(){
    var unreadCount = 0;
    allNotifications.forEach(function(item){
      if(isItemUnread(item)){
        unreadCount++;
      }
    });

    if(notifBadge){
      if(unreadCount > 0){
        notifBadge.textContent = unreadCount > 99 ? "99+" : unreadCount;
        notifBadge.hidden = false;
      } else {
        notifBadge.hidden = true;
      }
    }

    if(notifPill){
      if(unreadCount > 0){
        notifPill.textContent = unreadCount;
        notifPill.hidden = false;
      } else {
        notifPill.hidden = true;
      }
    }
  }

  function renderList(){
    if(!notifList) return;

    var filtered = allNotifications.filter(function(item){
      var unread = isItemUnread(item);
      if(currentFilter === "unread") return unread;
      if(currentFilter === "mention") return item.category === "mention" || item.type === "assign" || item.is_mine;
      return true;
    });

    if(filtered.length === 0){
      var emptyMsg = "도착한 알림이 없습니다.";
      if(currentFilter === "unread") emptyMsg = "확인하지 않은 새로운 알림이 없습니다.";
      if(currentFilter === "mention") emptyMsg = "배정되거나 멘션된 알림이 없습니다.";

      notifList.innerHTML = '<div class="notif-empty">' +
        '<div class="notif-empty-icon">🔔</div>' +
        '<div>' + emptyMsg + '</div>' +
      '</div>';
      return;
    }

    var html = "";
    filtered.forEach(function(item){
      var isUnread = isItemUnread(item);
      var typeClass = "type-" + (item.type || "assign");
      var tagHtml = "";
      if(item.tag){
        var tagTypeClass = "tag-" + (item.tag_type || "info");
        tagHtml = '<span class="notif-item-tag ' + tagTypeClass + '">' + escapeHtml(item.tag) + '</span>';
      }

      html += '<div class="notif-item ' + (isUnread ? 'unread' : '') + '" data-id="' + escapeHtml(item.id) + '" data-rec-id="' + escapeHtml(item.record_id || '') + '" data-tag="' + escapeHtml(item.tag || '') + '" data-title="' + escapeHtml(item.title || '') + '">' +
        '<div class="notif-item-icon ' + typeClass + '">' + getIconSvg(item.type) + '</div>' +
        '<div class="notif-item-content">' +
          '<div class="notif-item-title">' +
            '<span>' + escapeHtml(item.title) + '</span>' +
            tagHtml +
          '</div>' +
          '<div class="notif-item-desc" title="' + escapeHtml(item.desc || '') + '">' + escapeHtml(item.desc || '') + '</div>' +
          '<div class="notif-item-time">' + formatRelativeTime(item.time) + '</div>' +
        '</div>' +
      '</div>';
    });

    notifList.innerHTML = html;

    // Attach click listeners to notification items
    var itemEls = notifList.querySelectorAll(".notif-item");
    itemEls.forEach(function(el){
      el.addEventListener("click", function(){
        var id = el.getAttribute("data-id");
        var recId = el.getAttribute("data-rec-id");
        var tag = el.getAttribute("data-tag") || "";
        var title = el.getAttribute("data-title") || "";
        markIdAsRead(id);
        closeNotifMenu();

        // 1. 가입 승인 요청 알림 클릭 시 -> 설정 > 사용자 관리 탭으로 즉시 이동 & 승인 대기 필터 적용
        if(tag === "가입요청" || tag === "가입승인" || title.indexOf("가입 승인") !== -1 || title.indexOf("계정 발급") !== -1){
          if(typeof showTab === "function"){
            showTab("settings");
          }
          if(typeof switchSettingsTab === "function"){
            switchSettingsTab("users");
          }
          // 승인 대기 필터 자동 선택 & 새로고침
          setTimeout(function(){
            var filterStatus = document.getElementById("adminUserFilterStatus");
            if(filterStatus){
              filterStatus.value = "pending";
              if(typeof renderAdminUsersTable === "function"){
                renderAdminUsersTable();
              }
            }
            if(typeof loadAdminUsers === "function"){
              loadAdminUsers();
            }
          }, 100);
          return;
        }

        // 2. 업무 카드 알림 클릭 시 -> 대시보드 또는 캔버스 모달 열기
        if(recId){
          if(typeof window.showIssueInCanvas === "function"){
            window.showIssueInCanvas(recId);
          } else if(typeof showTab === "function"){
            showTab("dash");
          }
          return;
        }

        // 3. 기본 일반 알림 -> 대시보드로 이동
        if(typeof showTab === "function"){
          showTab("dash");
        }
      });
    });
  }

  function fetchNotifications(){
    if(typeof apiGet !== "function") return;
    apiGet("/api/notifications")
      .then(function(res){
        if(res && res.ok && Array.isArray(res.notifications)){
          allNotifications = res.notifications;
          updateBadge();
          renderList();

          // Check for new unread notifications to alert
          var newUnreadItems = [];
          allNotifications.forEach(function(item){
            if(isItemUnread(item) && !notifiedIds[item.id]){
              newUnreadItems.push(item);
              notifiedIds[item.id] = true;
            }
          });

          if(!isFirstFetch && newUnreadItems.length > 0){
            if(newUnreadItems.length === 1){
              triggerDesktopNotification(newUnreadItems[0]);
            } else {
              triggerDesktopNotification({
                title: "ARGOS WORKS",
                desc: newUnreadItems.length + "개의 새로운 중요 업무 알림이 도착했습니다.",
                tag: "신규알림"
              });
            }
            playNotifChime();
          }

          isFirstFetch = false;
        }
      })
      .catch(function(err){
        console.warn("Failed to fetch notifications:", err);
      });
  }

  function openNotifMenu(){
    if(!notifMenu) return;
    var accountMenu = document.getElementById("topbarAccountMenu");
    var avatarBtn = document.getElementById("topbarAvatarBtn");
    if(accountMenu && !accountMenu.hidden){
      accountMenu.hidden = true;
      if(avatarBtn) avatarBtn.setAttribute("aria-expanded", "false");
    }

    notifMenu.hidden = false;
    if(notifBtn) notifBtn.setAttribute("aria-expanded", "true");
    updatePushBanner();
    fetchNotifications();
  }

  function closeNotifMenu(){
    if(!notifMenu) return;
    notifMenu.hidden = true;
    if(notifBtn) notifBtn.setAttribute("aria-expanded", "false");
  }

  function toggleNotifMenu(e){
    if(e) e.stopPropagation();
    if(!notifMenu) return;
    if(notifMenu.hidden){
      openNotifMenu();
    } else {
      closeNotifMenu();
    }
  }

  function init(){
    notifBtn = document.getElementById("topbarNotifBtn");
    notifMenu = document.getElementById("topbarNotifMenu");
    notifList = document.getElementById("notifMenuList");
    notifBadge = document.getElementById("topbarNotifBadge");
    notifPill = document.getElementById("notifUnreadCountBadge");
    markAllBtn = document.getElementById("notifMarkAllReadBtn");
    soundBtn = document.getElementById("notifSoundToggleBtn");
    pushBanner = document.getElementById("notifPushBanner");
    enablePushBtn = document.getElementById("notifEnablePushBtn");
    testPushBtn = document.getElementById("notifTestPushBtn");

    if(!notifBtn || !notifMenu) return;

    notifBtn.addEventListener("click", toggleNotifMenu);

    if(markAllBtn){
      markAllBtn.addEventListener("click", function(e){
        e.stopPropagation();
        markAllAsRead();
      });
    }

    if(soundBtn){
      updateSoundBtn();
      soundBtn.addEventListener("click", function(e){
        e.stopPropagation();
        var nextState = !isSoundEnabled();
        setSoundEnabled(nextState);
        if(nextState){
          playNotifChime();
          if(typeof showToast === "function") showToast("알림음이 켜졌습니다.");
        } else {
          if(typeof showToast === "function") showToast("알림음이 음소거되었습니다.");
        }
      });
    }

    if(enablePushBtn){
      enablePushBtn.addEventListener("click", function(e){
        e.stopPropagation();
        requestPushPermission();
      });
    }

    if(testPushBtn){
      testPushBtn.addEventListener("click", function(e){
        e.stopPropagation();
        playNotifChime();
        if(!("Notification" in window)){
          if(typeof showToast === "function") showToast("현재 브라우저는 알림을 지원하지 않습니다.");
          return;
        }
        if(Notification.permission === "granted"){
          triggerDesktopNotification({
            title: "🔔 ARGOS WORKS 알림 테스트",
            desc: "데스크톱 실시간 알림 및 사운드가 정상 작동 중입니다.",
            tag: "테스트"
          });
          if(typeof showToast === "function") showToast("테스트 알림을 발송했습니다.");
        } else if(Notification.permission === "default"){
          requestPushPermission();
        } else {
          if(typeof showToast === "function") showToast("⚠️ 브라우저 주소창에서 알림 권한을 허용해주세요.");
        }
      });
    }

    updatePushBanner();

    // Tabs filter
    var tabsWrap = notifMenu.querySelector(".notif-menu-tabs");
    if(tabsWrap){
      tabBtns = tabsWrap.querySelectorAll(".notif-tab");
      tabBtns.forEach(function(tb){
        tb.addEventListener("click", function(e){
          e.stopPropagation();
          tabBtns.forEach(function(b){ b.classList.remove("active"); });
          tb.classList.add("active");
          currentFilter = tb.getAttribute("data-filter") || "all";
          renderList();
        });
      });
    }

    // Close on outside click
    document.addEventListener("click", function(e){
      if(!notifMenu.hidden && !notifMenu.contains(e.target) && !notifBtn.contains(e.target)){
        closeNotifMenu();
      }
    });

    // Close on Escape key
    document.addEventListener("keydown", function(e){
      if(e.key === "Escape" && !notifMenu.hidden){
        closeNotifMenu();
        notifBtn.focus();
      }
    });

    // Close notif menu if account avatar button is clicked
    var avatarBtn = document.getElementById("topbarAvatarBtn");
    if(avatarBtn){
      avatarBtn.addEventListener("click", function(){
        closeNotifMenu();
      });
    }

    // Initial fetch
    fetchNotifications();

    // Realtime SSE Notification Stream (Tức thì thay vì chờ 45 giây)
    function connectNotificationSSE(){
      var token = (typeof getSessionToken === "function" ? getSessionToken() : "") ||
                  (sessionStorage.getItem("argosToken") || localStorage.getItem("argosToken") || sessionStorage.getItem("jarvisToken") || localStorage.getItem("jarvisToken"));
      if(!token) return;

      var url = "/api/notifications/stream";
      var evtSource = new EventSource(url);

      evtSource.addEventListener("new_notification", function(e){
        try {
          var data = JSON.parse(e.data);
          var curUser = typeof getCurrentUser === "function" ? getCurrentUser() : null;
          var curEmail = (curUser && curUser.email) ? curUser.email.toLowerCase() : "";
          var curName = (curUser && curUser.name) ? curUser.name.trim() : "";

          // Nếu thông báo gửi cho chính mình hoặc gửi chung
          if(!data.recipient_email || data.recipient_email === curEmail || data.recipient_name === curName){
            fetchNotifications(); // Cập nhật lại chuông thông báo ngay lập tức
            if(typeof showToast === "function" && data.title){
              showToast("🔔 " + data.title);
            }
          }
        } catch(err){}
      });

      evtSource.onerror = function(){
        evtSource.close();
        // Tự động kết nối lại sau 10 giây nếu mất mạng
        setTimeout(connectNotificationSSE, 10000);
      };
    }

    connectNotificationSSE();

    // Fallback polling dài hơn (120s) dự phòng mạng ngắt SSE
    setInterval(fetchNotifications, 120000);
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.reloadNotifications = fetchNotifications;
})();
