/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // Runtime API URL is injected by Compose for server-side rendering.
};

module.exports = nextConfig;
