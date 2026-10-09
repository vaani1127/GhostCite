/* GhostCite web UI: submit a document, follow progress over Server-Sent Events, open the report. */
(function () {
  "use strict";

  var THEME_KEY = "ghostcite-theme";
  var LABELS = {
    VERIFIED: "Verified",
    METADATA_MISMATCH: "Metadata mismatch",
    NOT_FOUND: "Not found",
    UNPARSEABLE: "Unparseable",
    SKIPPED_BUDGET: "Skipped"
  };

  function storedTheme() {
    try { return window.localStorage.getItem(THEME_KEY); } catch (e) { return null; }
  }

  function applyTheme(theme) {
    if (theme) { document.documentElement.setAttribute("data-theme", theme); }
  }

  applyTheme(storedTheme());

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("check-form");
    var fileInput = document.getElementById("file");
    var textInput = document.getElementById("text");
    var submit = document.getElementById("submit");
    var sample = document.getElementById("sample");
    var errorBox = document.getElementById("error");
    var progress = document.getElementById("progress");
    var bar = document.getElementById("bar");
    var progressText = document.getElementById("progress-text");
    var ticks = document.getElementById("ticks");

    document.getElementById("theme").addEventListener("click", function () {
      var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      var current = document.documentElement.getAttribute("data-theme") || (dark ? "dark" : "light");
      var next = current === "dark" ? "light" : "dark";
      applyTheme(next);
      try { window.localStorage.setItem(THEME_KEY, next); } catch (e) { /* storage disabled */ }
    });

    function showError(message) {
      errorBox.textContent = message;
      errorBox.hidden = false;
      setBusy(false);
    }

    function setBusy(busy) {
      submit.disabled = busy || submit.dataset.locked === "true";
      sample.disabled = busy || sample.dataset.locked === "true";
      form.setAttribute("aria-busy", String(busy));
    }

    submit.dataset.locked = String(submit.disabled);
    sample.dataset.locked = String(sample.disabled);

    function follow(job) {
      progress.hidden = false;
      bar.max = Math.max(1, job.references);
      bar.value = 0;
      ticks.textContent = "";
      progressText.textContent = "Checking " + job.references + " references…";
      var events = new EventSource(job.events_url);
      events.addEventListener("progress", function (message) {
        var data = JSON.parse(message.data);
        bar.value = data.done;
        progressText.textContent = data.done + " of " + data.total + " references checked.";
        var item = document.createElement("li");
        item.className = "badge " + data.verdict;
        item.textContent = "#" + data.index + " " + (LABELS[data.verdict] || data.verdict);
        ticks.appendChild(item);
      });
      events.addEventListener("done", function (message) {
        events.close();
        window.location.assign(JSON.parse(message.data).url);
      });
      events.addEventListener("error", function (message) {
        events.close();
        var text = "The check failed.";
        if (message.data) { text = JSON.parse(message.data).message; }
        showError(text);
      });
    }

    function send(body) {
      errorBox.hidden = true;
      setBusy(true);
      fetch("/api/check", { method: "POST", body: body })
        .then(function (response) {
          return response.json().then(function (payload) { return { ok: response.status === 202, payload: payload }; });
        })
        .then(function (result) {
          if (!result.ok) { showError(result.payload.error || "The request was refused."); return; }
          follow(result.payload);
        })
        .catch(function () { showError("Could not reach the GhostCite server. Is it still running?"); });
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var hasFile = fileInput.files.length > 0;
      var hasText = textInput.value.trim().length > 0;
      if (hasFile === hasText) {
        showError(hasFile ? "Choose either a file or pasted text, not both." : "Upload a file or paste some references first.");
        return;
      }
      var body = new FormData();
      if (hasFile) { body.append("file", fileInput.files[0]); } else { body.append("text", textInput.value); }
      var mode = form.querySelector("input[name=mode]:checked");
      body.append("mode", mode ? mode.value : "live");
      send(body);
    });

    sample.addEventListener("click", function () {
      var body = new FormData();
      body.append("sample", "true");
      body.append("mode", "demo");
      send(body);
    });
  });
}());
