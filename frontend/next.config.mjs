import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: true },
  outputFileTracingRoot: dirname,
  // `next build` and `next dev` must never share an output directory: a build
  // started while the dev server is running overwrites `.next` and every page
  // starts failing with "Cannot find module './571.js'". Verified builds write
  // to `.next-build`, so a production build can be run alongside `npm run dev`.
  distDir: process.env.NEXT_DIST_DIR || '.next',
};

export default nextConfig;
