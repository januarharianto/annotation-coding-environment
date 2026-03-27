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

  // Escape key: navigate back (if a .ace-back link exists)
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    // Don't navigate if typing in an input or dialog is open
    var tag = document.activeElement && document.activeElement.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (document.querySelector("dialog[open]")) return;
    var back = document.querySelector(".ace-back");
    if (back) { window.location.href = back.href; }
  });

  // Listen for HTMX custom events that carry toast messages
  document.addEventListener("htmx:afterRequest", function (e) {
    var msg = e.detail.xhr && e.detail.xhr.getResponseHeader("X-ACE-Toast");
    if (msg) {
      window.aceToast(msg);
    }
  });
})();
