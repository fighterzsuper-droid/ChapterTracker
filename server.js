const express = require("express");
const multer = require("multer");
const path = require("path");
const fs = require("fs");

const app = express();
const PORT = process.env.PORT || 3000;
const uploadsDir = path.join(__dirname, "uploads");

if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir, { recursive: true });
}

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, uploadsDir);
  },
  filename: (req, file, cb) => {
    const timestamp = Date.now();
    const safeName = file.originalname.replace(/[^a-zA-Z0-9._-]/g, "_");
    cb(null, `${timestamp}-${safeName}`);
  }
});

const upload = multer({
  storage,
  limits: {
    fileSize: 1024 * 1024 * 1024 * 5
  }
});

app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

app.get("/api/files", (req, res) => {
  fs.readdir(uploadsDir, (err, files) => {
    if (err) {
      return res.status(500).json({ error: "Unable to read uploads" });
    }

    const payload = files
      .filter((file) => file !== ".gitkeep")
      .map((file) => {
        const filePath = path.join(uploadsDir, file);
        const stats = fs.statSync(filePath);
        return {
          name: file,
          size: stats.size,
          url: `/api/download/${encodeURIComponent(file)}`
        };
      })
      .sort((a, b) => b.size - a.size);

    return res.json(payload);
  });
});

app.post("/api/upload", upload.single("video"), (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: "No file uploaded" });
  }

  return res.status(201).json({
    name: req.file.filename,
    size: req.file.size,
    url: `/api/download/${encodeURIComponent(req.file.filename)}`
  });
});

app.get("/api/download/:filename", (req, res) => {
  const fileName = req.params.filename;
  const filePath = path.join(uploadsDir, fileName);

  if (!fs.existsSync(filePath)) {
    return res.status(404).send("File not found");
  }

  return res.download(filePath, fileName);
});

app.listen(PORT, () => {
  console.log(`Video share server running on http://localhost:${PORT}`);
});
