import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets the Docker build copy a minimal .next/standalone server instead of
  // shipping node_modules — see frontend/Dockerfile.
  output: "standalone",
};

export default nextConfig;
