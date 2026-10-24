/**
 * Shared DRF list-endpoint page walker.
 *
 * Backend list APIs are paginated with a hard per-page cap
 * (finance lists: 1000, student roster: 500). Any screen that fetched only
 * page 1 silently lost everything beyond the cap: the fee desk mislabeled
 * paid students as unpaid, and Fee Analytics under-counted receipts and
 * settlement percentages. fetchAllListPages follows EVERY server page so
 * callers work on complete data regardless of history size.
 *
 * Contract (mirrors a one-shot list response, including the old partial data
 * warning):
 *   - results   []                              — every row, in page order
 *   - count     number|null                     — authoritative DRF total
 *   - incomplete boolean                       — true if any page failed or
 *     was never fetched; results may then be a strict subset of `count`,
 *     so callers must warn instead of implying "complete".
 */
const MAX_LIST_PAGES = 200;

// Pages beyond page 1 are fetched concurrently once page 1 reveals the real
// total (fetching everything at once would hog the event loop/dial the server
// with up to 199 parallel requests; 6-at-a-time keeps latency close to
// sequential/6 without flooding the backend).
const PAGE_CONCURRENCY = 6;

function parseRows(data) {
  if (Array.isArray(data)) return { rows: data, next: null, count: null };
  return {
    rows: data?.results || [],
    next: data?.next || null,
    count: typeof data?.count === 'number' ? data.count : null,
  };
}

function chunk(arr, size) {
  const out = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

export async function fetchAllListPages(fetcher, baseParams) {
  const results = [];
  let count = null;
  let incomplete = false;

  // Page 1 lists the authoritative count; later pages may be fetched in
  // parallel against it.
  let first;
  try {
    const res = await fetcher({ ...baseParams, page: 1 });
    first = res?.data;
  } catch (err) {
    // No rows at all must never read as "empty list is the truth": flag
    // incomplete so callers can warn instead of showing a wrong verdict.
    console.error('listPages: page 1 fetch failed:', err);
    return { results, count, incomplete: true };
  }
  const firstParsed = parseRows(first);
  results.push(...firstParsed.rows);
  count = firstParsed.count ?? count;
  if (!firstParsed.next) {
    // Plain-array (non-paginated) endpoints end here.
    return { results, count, incomplete };
  }

  // How many pages are outstanding? Estimate from the authoritative count
  // and the served page size; cap hard to survive a pagination bug.
  const firstLen = firstParsed.rows.length || 1;
  let remainingPageCount = null;
  if (typeof count === 'number' && count > results.length) {
    remainingPageCount = Math.ceil((count - results.length) / firstLen);
  }
  const maxRemaining = MAX_LIST_PAGES - 1;
  if (remainingPageCount === null || remainingPageCount > maxRemaining) {
    // Unknown size or too large to trust: walk sequentially with the
    // per-page `next` link until it is exhausted or the guard trips.
    incomplete = remainingPageCount !== null; // maxRemaining tripped ⇒ incomplete
    let next = firstParsed.next;
    let page = 2;
    while (page <= MAX_LIST_PAGES && next) {
      try {
        const res = await fetcher({ ...baseParams, page });
        const parsed = parseRows(res?.data);
        results.push(...parsed.rows);
        next = parsed.next;
      } catch (err) {
        console.error('listPages: page', page, 'fetch failed:', err);
        incomplete = true;
        break;
      }
      page += 1;
    }
    return { results, count, incomplete };
  }

  // Known bound ≤ guard: fetch the remaining pages concurrently in chunks,
  // but always stitch results in page order no matter the settle order.
  const pageNumbers = [];
  for (let p = 2; p <= Math.min(remainingPageCount + 1, maxRemaining + 1); p += 1) {
    pageNumbers.push(p);
  }
  const perPage = new Map(); // pageNo -> rows
  for (const group of chunk(pageNumbers, PAGE_CONCURRENCY)) {
    const settled = await Promise.allSettled(
      group.map(p => fetcher({ ...baseParams, page: p })),
    );
    settled.forEach((res, idx) => {
      const p = group[idx];
      if (res.status === 'fulfilled') {
        perPage.set(p, parseRows(res.value?.data).rows);
      } else {
        console.error('listPages: page', p, 'fetch failed:', res.reason);
        incomplete = true;
      }
    });
  }

  for (let p = 2; p <= maxRemaining + 1; p += 1) {
    const rows = perPage.get(p);
    if (rows) results.push(...rows);
    else if (pageNumbers.includes(p)) {
      // Never fetched/failed: rows missing for that page. Values already in
      // `paged` gaps: earlier pages keep their rows, later ones (if any)
      // must NOT be silently dropped either — but a strict page-order fold
      // needs all preceding rows present. Fall back to best-effort order
      // with what we have; incomplete already flags the gap.
      const rest = pageNumbers.filter(x => x >= p).sort((a, b) => a - b)
        .flatMap(x => perPage.get(x) || []);
      results.push(...rest);
      break;
    }
  }

  return { results, count, incomplete };
}
