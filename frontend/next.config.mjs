/** @type {import('next').NextConfig} */
const isExport = process.env.NEXT_OUTPUT === "export";

const nextConfig = {
  reactStrictMode: true,
  output: isExport ? "export" : undefined,
  images: {
    unoptimized: isExport
  }
};

export default nextConfig;
