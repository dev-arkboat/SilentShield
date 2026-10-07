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

  // Staged multi-file picker: picks accumulate across dialog rounds
  // (a bare <input multiple> would replace the old picks each round)
  // with per-file remove buttons. Nothing uploads until submit.
  document.querySelectorAll('input[type="file"][multiple]').forEach(function (input) {
    var form = input.closest("form");
    var box = form ? form.querySelector("[data-preview]") : null;
    var counter = form ? form.querySelector("[data-count]") : null;
    var staged = new DataTransfer();

    function kb(n) { return Math.round((n || 0) / 1024) + " KB"; }

    function render() {
      var files = Array.prototype.slice.call(staged.files);
      input.files = staged.files;
      if (counter) {
        counter.textContent = files.length === 0
          ? ""
          : files.length + (files.length === 1 ? " file staged." : " files staged.");
      }
      if (!box) return;
      box.innerHTML = "";
      files.forEach(function (f, i) {
        var fig = document.createElement("figure");
        if (f.type.indexOf("image/") === 0) {
          var img = document.createElement("img");
          img.alt = "Staged evidence preview";
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
        cap.textContent = kb(f.size);
        fig.appendChild(cap);
        var x = document.createElement("button");
        x.type = "button";
        x.className = "pv-x";
        x.setAttribute("aria-label", "Remove " + f.name);
        x.textContent = "✕";
        x.addEventListener("click", function () {
          staged.items.remove(i);
          render();
        });
        fig.appendChild(x);
        box.appendChild(fig);
      });
    }

    input.addEventListener("change", function () {
      Array.prototype.slice.call(input.files).forEach(function (f) {
        var dup = Array.prototype.slice.call(staged.files).some(function (g) {
          return g.name === f.name && g.size === f.size && g.lastModified === f.lastModified;
        });
        if (!dup) staged.items.add(f);
      });
      render();
    });
  });

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
