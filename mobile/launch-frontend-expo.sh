#!/bin/bash
# Platform 'mobile' supervisor service interceptor (single-codebase, single-Metro).
#
# The readonly supervisor config runs `yarn expo start --port 3001` inside
# /app/mobile; package.json's "expo" script routes here. The preview pod has an
# 8 GB cgroup memory cap, so we do NOT start a second Metro. Instead we run a
# tiny reverse proxy (port 3001 -> 3000): the web Metro in /app/frontend is an
# Expo dev server that already serves native (Expo Go) manifests and bundles.
# Supervisor args ("start --port 3001") are intentionally ignored.

exec node /app/mobile/metro-proxy.js
