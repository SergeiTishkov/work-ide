// The application funnel: what can follow what, and what each step records.
// One definition for the interface (which buttons to show, the timeline) and
// the main process (which writes the database) — so they cannot disagree.
// A plain script, like the locale: it loads in Electron, a browser and node.
//
// A record is the feedback of one vacancy:
//   { status, at, rejectedReason, buggedReason, appliedAt,
//     contactComment, contactAt, interviewComments[], interviewAt[],
//     finalComment, finalAt }
// A step that happened keeps a comment that is never null: '' means it
// happened and nothing was written about it.
(function (root, factory) {
  const value = factory();
  if (typeof module === 'object' && module.exports) module.exports = value;
  else root.WorkIdeFunnel = value;
}(typeof self !== 'undefined' ? self : this, () => {
  const FUNNEL = ['applied', 'contacted', 'interview', 'awaiting_final'];
  const NEXT = {
    applied: ['contacted'],
    // Straight to the final word is allowed: a test task can take the place
    // of an interview.
    contacted: ['interview', 'awaiting_final'],
    interview: ['interview', 'awaiting_final'],
    awaiting_final: [],
  };
  const POSITIVE_KINDS = ['contact', 'interview', 'final'];
  const NEGATIVE_KINDS = ['rejected', 'bugged'];

  function nextSteps(status) {
    return NEXT[status] || [];
  }

  function copy(record) {
    return {
      ...record,
      interviewComments: [...(record.interviewComments || [])],
      interviewAt: [...(record.interviewAt || [])],
    };
  }

  // One step forward; the comment may be empty, never null.
  function advance(record, step, comment, now) {
    if (!nextSteps(record.status).includes(step)) {
      throw new Error(`cannot go from ${record.status} to ${step}`);
    }
    const text = comment == null ? '' : String(comment);
    const next = copy(record);
    next.status = step;
    next.at = now;
    if (step === 'contacted') {
      next.contactComment = text;
      next.contactAt = now;
    } else if (step === 'interview') {
      next.interviewComments.push(text);
      next.interviewAt.push(now);
    } else if (step === 'awaiting_final') {
      next.finalComment = text;
      next.finalAt = now;
    }
    return next;
  }

  // "Undo": one step back, forgetting what that step recorded.
  function stepBack(record, now) {
    const back = copy(record);
    switch (record.status) {
      case 'awaiting_final':
        back.finalComment = null;
        back.finalAt = null;
        back.status = back.interviewComments.length ? 'interview' : 'contacted';
        break;
      case 'interview':
        back.interviewComments.pop();
        back.interviewAt.pop();
        back.status = back.interviewComments.length ? 'interview' : 'contacted';
        break;
      case 'contacted':
        back.contactComment = null;
        back.contactAt = null;
        back.status = 'applied';
        break;
      default:   // applied, rejected, bugged, expired: back to no feedback
        back.status = 'new';
        back.appliedAt = null;
        back.rejectedReason = null;
        back.buggedReason = null;
    }
    back.at = now;
    return back;
  }

  // Rewrites one comment. A negative reason left empty is no reason (null) and
  // editing it dates the feedback anew, so /feedback reviews the new words.
  function editComment(record, kind, index, text, now) {
    const next = copy(record);
    const value = text == null ? '' : String(text);
    if (kind === 'contact') next.contactComment = value;
    else if (kind === 'final') next.finalComment = value;
    else if (kind === 'interview') {
      if (!(index >= 0 && index < next.interviewComments.length)) {
        throw new Error(`no interview ${index}`);
      }
      next.interviewComments[index] = value;
    } else if (NEGATIVE_KINDS.includes(kind)) {
      if (record.status !== kind) throw new Error(`the vacancy is not ${kind}`);
      next[kind === 'rejected' ? 'rejectedReason' : 'buggedReason'] = value.trim() ? value : null;
      next.at = now;
    } else {
      throw new Error(`unknown comment kind: ${kind}`);
    }
    return next;
  }

  // The steps to show under a vacancy, in order, each with its date:
  // { kind, index?, at, comment (null when the step has none), editable }.
  function timeline(record) {
    const steps = [];
    const appliedAt = record.appliedAt || (record.status === 'applied' ? record.at : null);
    if (appliedAt && record.status !== 'new') {
      steps.push({ kind: 'applied', at: appliedAt, comment: null, editable: false });
    }
    if (record.contactAt) {
      steps.push({ kind: 'contact', at: record.contactAt, comment: record.contactComment ?? '', editable: true });
    }
    (record.interviewComments || []).forEach((comment, index) => {
      steps.push({
        kind: 'interview', index, at: (record.interviewAt || [])[index] || null,
        comment: comment ?? '', editable: true,
      });
    });
    if (record.finalAt) {
      steps.push({ kind: 'final', at: record.finalAt, comment: record.finalComment ?? '', editable: true });
    }
    if (record.status === 'rejected' || record.status === 'bugged') {
      const reason = record.status === 'rejected' ? record.rejectedReason : record.buggedReason;
      steps.push({ kind: record.status, at: record.at, comment: reason || '', editable: true });
    }
    if (record.status === 'expired') {
      steps.push({ kind: 'expired', at: record.at, comment: null, editable: false });
    }
    return steps;
  }

  return {
    FUNNEL, POSITIVE_KINDS, NEGATIVE_KINDS, nextSteps, advance, stepBack, editComment, timeline,
  };
}));
