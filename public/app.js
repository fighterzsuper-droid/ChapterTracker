const uploadForm = document.getElementById("uploadForm");
const statusEl = document.getElementById("status");
const fileList = document.getElementById("fileList");
const refreshBtn = document.getElementById("refresh");
const emptyState = document.getElementById("emptyState");

const formatBytes = (bytes) => {
  if (bytes === 0) {
    return "0 B";
  }

  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(1)} ${sizes[i]}`;
};

const renderFiles = (files) => {
  fileList.innerHTML = "";

  if (!files.length) {
    emptyState.style.display = "block";
    return;
  }

  emptyState.style.display = "none";
  files.forEach((file) => {
    const item = document.createElement("li");
    item.className = "file-item";

    const meta = document.createElement("div");
    meta.className = "file-meta";

    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = file.name;

    const size = document.createElement("span");
    size.className = "file-size";
    size.textContent = formatBytes(file.size);

    const link = document.createElement("a");
    link.href = file.url;
    link.textContent = "Download";
    link.className = "download-link";
    link.download = file.name;

    meta.appendChild(name);
    meta.appendChild(size);

    item.appendChild(meta);
    item.appendChild(link);

    fileList.appendChild(item);
  });
};

const loadFiles = async () => {
  try {
    const response = await fetch("/api/files");
    const files = await response.json();
    renderFiles(files);
  } catch (error) {
    statusEl.textContent = "Unable to load files.";
    statusEl.classList.add("error");
  }
};

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusEl.textContent = "Uploading...";
  statusEl.classList.remove("error");

  const formData = new FormData(uploadForm);

  try {
    const response = await fetch("/api/upload", {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      throw new Error("Upload failed");
    }

    statusEl.textContent = "Upload complete. Your friend can download it now.";
    uploadForm.reset();
    await loadFiles();
  } catch (error) {
    statusEl.textContent = "Upload failed. Please try again.";
    statusEl.classList.add("error");
  }
});

refreshBtn.addEventListener("click", loadFiles);

loadFiles();
