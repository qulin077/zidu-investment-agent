/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    API_BASE: process.env.API_BASE ?? "http://127.0.0.1:8787",
  },
};

export default nextConfig;
