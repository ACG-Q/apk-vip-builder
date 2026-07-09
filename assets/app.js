var CONFIG = {
  repo: "ACG-Q/apk-vip-builder",
};

var APP_STORES = [
  { name: "豌豆荚", url: "https://www.wandoujia.com", icon: "📦" },
  { name: "APKPure", url: "https://apkpure.net", icon: "🟣" },
  { name: "Google Play", url: "https://play.google.com/store/apps", icon: "▶" },
  { name: "酷安", url: "https://www.coolapk.com", icon: "📱" },
  { name: "APKMirror", url: "https://www.apkmirror.com", icon: "🔍" },
  { name: "F-Droid", url: "https://f-droid.org", icon: "🤖" },
];

var KNOWN_APPS = {
  "com.habits.todolist.plan.wish": "yuanqi",
  "cn.skyrin.ntfh": "ntfh",
  "com.catchingnow.np": "filterbox",
  "com.lwjlol.imagehosting": "xiaobai-image-host",
};

var currentApkInfo = null;
var currentApkFile = null;
var currentApkBuffer = null;

document.addEventListener("DOMContentLoaded", function() {
  document.getElementById("version-badge").textContent = "v" + (AXML.VERSION || "?");
  renderStoreLinks();
});

function showUpload() {
  hideAll("upload-section");
  document.getElementById("upload-section").classList.remove("hidden");
}

function hideAll(keep) {
  var ids = ["upload-section", "metadata-section", "result-section"];
  ids.forEach(function(id) {
    document.getElementById(id).classList.add("hidden");
  });
}

/* ─── Toast ─── */
function showToast(message, type) {
  var container = document.getElementById("toast-container");
  var el = document.createElement("div");
  el.className = "toast toast-" + (type || "success");
  el.textContent = message;
  el.setAttribute("role", "alert");
  container.appendChild(el);
  requestAnimationFrame(function() {
    el.classList.add("visible");
  });
  setTimeout(function() {
    el.classList.remove("visible");
    setTimeout(function() { el.remove(); }, 200);
  }, 3500);
}

/* ─── APK ─── */
function handleDrop(event) {
  event.preventDefault();
  var file = event.dataTransfer.files[0];
  if (file) handleFile(file);
}

function handleFile(file) {
  if (!file.name.endsWith(".apk") && !file.name.endsWith(".xapk")) {
    showToast("请上传 .apk 或 .xapk 文件", "error");
    return;
  }
  currentApkFile = file;
  hideAll("metadata-section");
  document.getElementById("metadata-section").classList.remove("hidden");
  document.getElementById("upload-progress").classList.remove("hidden");
  document.getElementById("progress-fill").style.width = "30%";
  document.getElementById("progress-text").textContent = "解析 APK 中...";
  parseApk(file).then(function(info) {
    currentApkInfo = info;
    displayMetadata(info);
    document.getElementById("upload-progress").classList.add("hidden");
  }).catch(function(err) {
    document.getElementById("progress-text").textContent = "解析失败";
    showToast(err.message, "error");
  });
}

async function parseApk(file) {
  var buf = await file.arrayBuffer();
  currentApkBuffer = buf;
  var zip = await JSZip.loadAsync(buf);

  var mfEntry = zip.file("manifest.json");
  if (mfEntry) {
    var mf = JSON.parse(await mfEntry.async("string"));
    var info = {
      package: mf.package_name || "",
      versionCode: parseInt(mf.version_code) || 0,
      versionName: mf.version_name || "",
      label: mf.name || mf.package_name || "",
      size: file.size,
      app: KNOWN_APPS[mf.package_name] || null,
    };
    if (!info.package) throw new Error("无法解析包名");
    return info;
  }

  var entry = zip.file("AndroidManifest.xml");
  if (!entry) throw new Error("AndroidManifest.xml not found");
  var raw = await entry.async("uint8array");
  var info = AXML.parse(raw);
  if (!info.package) throw new Error("无法解析包名");
  var label = info.label;
  if (!label || label.startsWith("@")) {
    try {
      var s = await zip.file("res/values/strings.xml")?.async("string");
      var m = s?.match(/<string\s+name="app_name">([^<]+)<\/string>/);
      if (m) label = m[1];
    } catch (_) {}
  }
  info.label = label || info.package;
  info.size = file.size;
  info.app = KNOWN_APPS[info.package] || null;
  return info;
}

function displayMetadata(info) {
  document.getElementById("meta-package").textContent = info.package;
  document.getElementById("meta-version-name").textContent = info.versionName || "?";
  document.getElementById("meta-version-code").textContent = info.versionCode ?? "?";
  document.getElementById("meta-label").textContent = info.label;
  document.getElementById("meta-size").textContent = formatSize(info.size);
  var appEl = document.getElementById("meta-app");
  if (info.app) {
    appEl.innerHTML = '<span class="meta-badge supported">' + info.app + "</span>";
  } else {
    appEl.innerHTML = '<span class="meta-badge unsupported">未知</span>';
  }
  var btn = document.getElementById("submit-btn");
  btn.disabled = !info.app;
  btn.textContent = info.app ? "创建构建请求 (" + info.app + ")" : "不支持的应用";
}

function renderStoreLinks() {
  var el = document.getElementById("store-links");
  el.innerHTML = APP_STORES.map(function(s) {
    return '<a class="store-link" href="' + s.url + '" target="_blank" rel="noopener">' +
      '<span class="store-icon">' + s.icon + '</span>' +
      '<span class="store-name">' + s.name + '</span>' +
      '</a>';
  }).join("");
}

function formatSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}

/* ─── Issue ─── */
function createIssue() {
  if (!currentApkInfo || !currentApkFile) return;
  if (!currentApkInfo.app) {
    showToast("不支持的应用", "error");
    return;
  }
  var info = currentApkInfo;
  var body = [
    "## APK 自动解析结果",
    "",
    "### 应用",
    info.app,
    "",
    "### 包名",
    info.package,
    "",
    "### 版本名",
    info.versionName || "?",
    "",
    "### 版本号",
    info.versionCode || "?",
    "",
    "### 文件大小",
    formatSize(info.size),
    "",
    "---",
    "",
    "请将下载的 `.apk.zip` 文件拖拽到此处上传。",
  ].join("\n");

  var title = "[APK] " + info.app + " " + (info.versionName || "") + " (" + (info.versionCode || "?") + ")";
  var url = "https://github.com/" + CONFIG.repo + "/issues/new?labels=apk-auto&title=" + encodeURIComponent(title) + "&body=" + encodeURIComponent(body);
  window.open(url, "_blank");
  showResult(info.app);
}

/* ─── Result ─── */
function showResult(app) {
  var info = currentApkInfo;
  var filename = (info.app || info.package) + "." + (info.versionName || "0") + ".apk.zip";
  hideAll("result-section");
  document.getElementById("result-section").classList.remove("hidden");
  document.getElementById("result-body").innerHTML =
    "<p>应用: <strong>" + app + "</strong></p>" +
    '<p style="margin-top:12px;font-size:14px;color:var(--text-secondary)">已在新标签页打开 Issue 页面。</p>' +
    '<p style="margin-top:8px;font-size:14px;color:var(--text-secondary)">将已下载的 <strong>' + filename + '</strong> 拖入 Issue 编辑器，然后提交。</p>' +
    '<p style="margin:12px 0 8px"><button class="btn-primary" onclick="downloadApk()">重新下载 .apk.zip</button></p>' +
    '<p style="margin-top:8px;font-size:13px;color:var(--text-muted)">提交后将在几分钟内自动触发构建。</p>' +
    '<p><button class="btn-ghost" onclick="startOver()" style="margin-top:16px">上传其他 APK</button></p>';
  downloadApk();
}

function downloadApk() {
  if (!currentApkBuffer || !currentApkInfo) return;
  var info = currentApkInfo;
  var filename = (info.app || info.package) + "." + (info.versionName || "0") + ".apk.zip";
  var blob = new Blob([currentApkBuffer], { type: "application/zip" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(function() { URL.revokeObjectURL(url); }, 60000);
}

function startOver() {
  currentApkInfo = null;
  currentApkFile = null;
  currentApkBuffer = null;
  hideAll("upload-section");
  document.getElementById("upload-section").classList.remove("hidden");
}
