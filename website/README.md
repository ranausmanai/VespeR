# vesper.run landing page

Static site files for the marketing/docs homepage.

## Local preview

```bash
cd website
python -m http.server 8080
```

Open `http://127.0.0.1:8080`.

## Deploy on DigitalOcean (simple)

1. Copy `website/` to your server.
2. Serve it with Nginx as static files (root pointing to this folder).
3. Set DNS `A` record for `vesper.run` to your server IP.
4. Add TLS with Let's Encrypt (Certbot).

