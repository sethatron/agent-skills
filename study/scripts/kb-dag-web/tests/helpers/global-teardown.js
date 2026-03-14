module.exports = async function globalTeardown() {
  if (globalThis.__TEST_SERVER__) globalThis.__TEST_SERVER__.close();
};
