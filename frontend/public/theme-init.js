// Runs before first paint (loaded synchronously from <head>) so a saved theme never flashes the default.
// An external file rather than an inline script: the CSP allows script-src 'self' only.
(function () {
  var ids = ["soldermask", "instrument", "tty", "datasheet"];
  var t = "soldermask";
  try {
    var saved = localStorage.getItem("cg.theme");
    if (ids.indexOf(saved) >= 0) t = saved;
  } catch (e) {}
  document.documentElement.setAttribute("data-theme", t);
})();
