# Video Share Vault

A lightweight Node/Express app that lets you upload high-quality video files and share download links.

## Getting started

```bash
npm install
npm start
```

Open `http://localhost:3000` to upload and download videos.

## Deploy online (quick option)

If you want your friend to access the site online, deploy it to a Node-friendly host such as Render or Railway.

### Render (free tier)

1. Push this repo to GitHub.
2. Create a **Web Service** on Render and connect the repo.
3. Set the build command to `npm install` and the start command to `npm start`.
4. Deploy, then share the generated URL with your friend.

### Railway (free tier)

1. Push this repo to GitHub.
2. Create a new Railway project from the repo.
3. Ensure the start command is `npm start`.
4. Deploy, then share the generated URL.

## Notes

- Uploaded files are stored in the `uploads/` directory with timestamped names.
- File uploads are not compressed, so the original quality is preserved.
- This is a simple self-hosted app; consider adding authentication if you plan to share the link more broadly.
