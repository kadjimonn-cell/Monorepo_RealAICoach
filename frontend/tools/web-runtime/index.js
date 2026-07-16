const express = require('express');
const serveStatic = require('serve-static');
const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = {
  express,
  serveStatic,
  createProxyMiddleware,
};