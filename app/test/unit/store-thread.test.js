'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { StoreThread } = require('../../main/store-thread');
const { SCHEMA_DIR, standardDatabase, tempDir } = require('../helpers/fixture-db');

const VIEW = { segments: null, statuses: ['new'], fresh: ['fresh'], sources: null, fits: null };

test('the store on its own thread answers as the store does, in the order asked', async () => {
  const file = standardDatabase(path.join(tempDir(), 'test.sqlite'));
  const thread = new StoreThread({ schemaDir: SCHEMA_DIR, databases: () => ({ test: file }) });
  try {
    const rows = await thread.call('listing', 'test', VIEW, {});
    assert.deepEqual(rows.map((r) => r.id), ['new0', 'new1', 'new2']);
    // an answer written, then the list read: one after the other
    const [, after] = await Promise.all([
      thread.call('setFeedback', 'test', 'new0', 'rejected', 'travel'),
      thread.call('listing', 'test', VIEW, {}),
    ]);
    assert.deepEqual(after.map((r) => r.id), ['new1', 'new2']);
    assert.deepEqual((await thread.call('segments', 'other')).segments, []);
    await assert.rejects(thread.call('setFeedback', 'test', 'new0', 'maybe'), Error);
    await thread.call('closeAll');
  } finally {
    thread.close();
  }
});
