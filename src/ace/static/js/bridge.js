/**
 * ACE Bridge — client-side utilities for the FastAPI + HTMX app.
 */

(function () {
  "use strict";

  /**
   * Show a toast notification.
   * @param {string} message  Text to display.
   * @param {number} [duration=3000]  Auto-dismiss milliseconds.
   */
  window.aceToast = function (message, duration) {
    duration = duration || 3000;
    var container = document.getElementById("toast");
    if (!container) return;

    var el = document.createElement("div");
    el.className = "toast-msg";
    el.textContent = message;
    container.appendChild(el);

    setTimeout(function () {
      el.classList.add("fade-out");
      el.addEventListener("transitionend", function () {
        el.remove();
      });
    }, duration);
  };

  // Listen for HTMX custom events that carry toast messages
  document.addEventListener("htmx:afterRequest", function (e) {
    var msg = e.detail.xhr && e.detail.xhr.getResponseHeader("X-ACE-Toast");
    if (msg) {
      window.aceToast(msg);
    }
  });
})();
