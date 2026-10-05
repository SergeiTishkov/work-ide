'use strict';
// The filters are drop-downs of the app's own (renderer/app.js, dropdown()),
// not <select>: a person opens the box and clicks an option, and the chosen
// value is the box's data-value.
async function choose(page, testid, value) {
  await page.getByTestId(testid).click();
  await page.getByTestId(`${testid}-menu`).locator(`[role="option"][data-value="${value}"]`).click();
}

module.exports = { choose };
