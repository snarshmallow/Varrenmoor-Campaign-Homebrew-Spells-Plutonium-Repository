// Minimal CSInterface shim (hand-written; no Adobe download). Covers what main.js needs.
function CSInterface() {}
CSInterface.prototype.evalScript = function (script, callback) {
  if (callback === null || callback === undefined) callback = function () {};
  window.__adobe_cep__.evalScript(script, callback);
};
CSInterface.prototype.getSystemPath = function (type) {
  var p = decodeURIComponent(window.__adobe_cep__.getSystemPath(type));
  return p.replace(/^file:\/\/\//, "").replace(/^file:\/\//, "");
};
var SystemPath = { EXTENSION: "extension", USER_DATA: "userData", HOST_APPLICATION: "hostApplication" };
// Used by the reload button's last-resort fallback (version_ui.js); the real CEP object has these, the test stub may not.
CSInterface.prototype.closeExtension = function () { window.__adobe_cep__.closeExtension(); };
CSInterface.prototype.requestOpenExtension = function (id, params) { window.__adobe_cep__.requestOpenExtension(id, params || ""); };
CSInterface.prototype.getExtensionID = function () { return window.__adobe_cep__.getExtensionId(); };
