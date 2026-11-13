/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  distDir: process.env.QUANT_NEXT_DIST_DIR || ".next",
  experimental: { cpus: 2 },
  output: "standalone",
};

export default nextConfig;
