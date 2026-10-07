/* Silent Shield — vanilla JS only. No trackers, no fingerprinting.
   - Mobile nav toggle
   - Report file previews (client-side only until submit)
   - Confirm for exclusive claim
   - Privacy-safe ad viewability beacons + localStorage frequency caps + dismiss
*/
(function () {
  "use strict";

  function csrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  // Mobile nav
  var toggle = document.getElementById("navToggle");
  var nav = document.getElementById("siteNav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // Claim confirm
  document.querySelectorAll("[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (!window.confirm(f.getAttribute("data-confirm"))) e.preventDefault();
    });
  });

  // Evidence preview (images only; video/audio shown as labelled chips)
  var input = document.getElementById("id_files");
  var preview = document.getElementById("preview");
  if (input && preview) {
    input.addEventListener("change", function () {
      preview.innerHTML = "";
      Array.prototype.slice.call(input.files || []).slice(0, 12).forEach(function (f) {
        var fig = document.createElement("figure");
        if (f.type.indexOf("image/") === 0) {
          var img = document.createElement("img");
          img.alt = "Selected evidence preview";
          img.src = URL.createObjectURL(f);
          img.onload = function () { URL.revokeObjectURL(img.src); };
          fig.appendChild(img);
        } else {
          var p = document.createElement("p");
          p.textContent = (f.type.indexOf("video/") === 0 ? "VIDEO · " : "AUDIO · ") + f.name;
          p.style.cssText = "font-size:.8rem;padding:10px;margin:0";
          fig.appendChild(p);
        }
        var cap = document.createElement("figcaption");
        cap.textContent = Math.round((f.size || 0) / 1024) + " KB";
        fig.appendChild(cap);
        preview.appendChild(fig);
      });
    });
  }

  // Nav dropdowns (<details>): one open at a time, close on outside tap / Escape
  var drops = document.querySelectorAll(".nav-drop");
  drops.forEach(function (d) {
    d.addEventListener("toggle", function () {
      if (d.open) drops.forEach(function (o) { if (o !== d) o.open = false; });
    });
  });
  document.addEventListener("click", function (e) {
    drops.forEach(function (d) {
      if (d.open && !d.contains(e.target)) d.open = false;
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") drops.forEach(function (d) { d.open = false; });
  });

  // Auto-hiding header: slides away scrolling down, returns scrolling up.
  // Skipped entirely under reduced motion (header simply stays put).
  var header = document.getElementById("siteHeader");
  if (header && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    var lastY = window.scrollY || 0;
    var ticking = false;
    var onScroll = function () {
      var y = window.scrollY || 0;
      var menuOpen = nav && nav.classList.contains("open");
      if (!menuOpen) {
        if (y > lastY && y > 160) header.classList.add("nav-hidden");
        else if (y < lastY) header.classList.remove("nav-hidden");
      }
      lastY = y;
      ticking = false;
    };
    window.addEventListener("scroll", function () {
      if (!ticking) {
        window.requestAnimationFrame(onScroll);
        ticking = true;
      }
    }, { passive: true });
  }

  // Calm scroll reveals (disabled entirely under reduced motion)
  if ("IntersectionObserver" in window &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    var revealed = document.querySelectorAll(".reveal");
    var rio = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add("in");
          rio.unobserve(en.target);
        }
      });
    }, { threshold: 0.08 });
    revealed.forEach(function (el) { rio.observe(el); });
  } else {
    document.querySelectorAll(".reveal").forEach(function (el) {
      el.classList.add("in");
    });
  }

  // Focus the first field error after a failed submit (server-rendered)
  var firstErr = document.querySelector(".err");
  if (firstErr) {
    var box = firstErr.closest("form");
    var field = box ? box.querySelector("input, select, textarea") : null;
    if (field) field.focus({ preventScroll: false });
  }

  // ---- Ads: viewability beacon (IntersectionObserver), dismiss, frequency cap
  function capped(key, max) {
    try {
      var n = parseInt(window.localStorage.getItem(key) || "0", 10) || 0;
      return n >= max;
    } catch (e) { return false; }
  }
  function bump(key) {
    try {
      var n = parseInt(window.localStorage.getItem(key) || "0", 10) || 0;
      window.localStorage.setItem(key, String(n + 1));
    } catch (e) { /* private mode: ignore */ }
  }

  var ads = document.querySelectorAll(".ad[data-ad]");
  ads.forEach(function (el) {
    var id = el.getAttribute("data-ad");
    var slot = el.getAttribute("data-slot") || "general";
    var capKey = "ss_adcap_" + slot;
    if (capped(capKey, 5)) { el.setAttribute("data-hidden", "1"); return; }
    if (!("IntersectionObserver" in window)) return;
    var seen = false;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting && !seen) {
          seen = true;
          bump(capKey);
          try {
            fetch("/ads/imp/" + id + "/", {
              method: "POST",
              headers: { "X-CSRFToken": csrf() }
            });
          } catch (e) { /* beacon best-effort */ }
          io.disconnect();
        }
      });
    }, { threshold: 0.5 });
    io.observe(el);
  });

  document.querySelectorAll("[data-dismiss]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var id = btn.getAttribute("data-dismiss");
      var box = btn.closest(".ad");
      if (box) box.setAttribute("data-hidden", "1");
      try {
        fetch("/ads/dismiss/" + id + "/", { method: "POST", headers: { "X-CSRFToken": csrf() } });
      } catch (e) { /* ignore */ }
    });
  });
})();
