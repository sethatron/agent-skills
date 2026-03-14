const { generateFixture, startServer, TEST_PORT } = require('./server');

module.exports = async function globalSetup() {
  await generateFixture();
  const server = await startServer(TEST_PORT);
  globalThis.__TEST_SERVER__ = server;
};
