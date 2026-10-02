// The application funnel: what can follow what, and what each step records.
// One definition for the interface (which buttons to show, the timeline) and
// the main process (which writes the database) — so they cannot disagree.
// A plain script, like the locale: it loads in Electron, a browser and node.
//
// A record is the feedback of one vacancy:
//   { status, at, rejectedReason, buggedReason, appliedAt,
//     contactComment, contactAt, interviewComments[], interviewAt[],
//     finalComment, finalAt, offerComment, offerAt,
//     offeredComment, offeredAt, startedComment, startedAt,
//     declinedComment, declinedAt }
// ("offer" is the wait for the offer; "offered" is the offer itself.)
// A step that happened keeps a comment that is never null: '' means it
// happened and nothing was written about it.
(function (root, factory) {
  const value = factory();
  if (typeof module === 'object' && module.exports) module.exports = value;
  else root.WorkIdeFunnel = value;
}(typeof self !== 'undefined' ? self : this, () => {
  const FUNNEL = ['applied', 'contacted', 'interview', 'awaiting_final', 'awaiting_offer',
    'offered', 'started', 'declined'];
  // "declined" is the employer's no. It can come at any step while an
  // application is alive, and it ends the application: nothing follows it.
  const NEXT = {
    applied: ['contacted', 'declined'],
    // Straight to the final resolution is allowed: a test task can take the
    // place of an interview.
    contacted: ['interview', 'awaiting_final', 'declined'],
    interview: ['interview', 'awaiting_final', 'declined'],
    // Approved, but the offer itself can take a week or more to arrive.
    awaiting_final: ['awaiting_offer', 'declined'],
    // An offer can still fall through.
    awaiting_offer: ['offered', 'declined'],
    offered: ['started'],
    started: [],
    declined: [],
  };
  const POSITIVE_KINDS = ['contact', 'interview', 'final', 'offer', 'offered', 'started', 'declined'];
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
    } else if (step === 'awaiting_offer') {
      next.offerComment = text;
      next.offerAt = now;
    } else if (step === 'offered') {
      next.offeredComment = text;
      next.offeredAt = now;
    } else if (step === 'started') {
      next.startedComment = text;
      next.startedAt = now;
    } else if (step === 'declined') {
      next.declinedComment = text;
      next.declinedAt = now;
    }
    return next;
  }

  // Where an application stood before its latest step, from what it recorded.
  function stageBefore(record) {
    if (record.offerAt) return 'awaiting_offer';
    if (record.finalAt) return 'awaiting_final';
    if ((record.interviewComments || []).length) return 'interview';
    if (record.contactAt) return 'contacted';
    return 'applied';
  }

  // "Undo": one step back, forgetting what that step recorded.
  function stepBack(record, now) {
    const back = copy(record);
    switch (record.status) {
      case 'started':
        back.startedComment = null;
        back.startedAt = null;
        back.status = 'offered';
        break;
      case 'offered':
        back.offeredComment = null;
        back.offeredAt = null;
        back.status = 'awaiting_offer';
        break;
      case 'declined':
        back.declinedComment = null;
        back.declinedAt = null;
        back.status = stageBefore(back);
        break;
      case 'awaiting_offer':
        back.offerComment = null;
        back.offerAt = null;
        back.status = 'awaiting_final';
        break;
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
    else if (kind === 'offer') next.offerComment = value;
    else if (kind === 'offered') next.offeredComment = value;
    else if (kind === 'started') next.startedComment = value;
    else if (kind === 'declined') next.declinedComment = value;
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
    if (record.offerAt) {
      steps.push({ kind: 'offer', at: record.offerAt, comment: record.offerComment ?? '', editable: true });
    }
    if (record.offeredAt) {
      steps.push({ kind: 'offered', at: record.offeredAt, comment: record.offeredComment ?? '', editable: true });
    }
    if (record.startedAt) {
      steps.push({ kind: 'started', at: record.startedAt, comment: record.startedComment ?? '', editable: true });
    }
    if (record.declinedAt) {
      steps.push({ kind: 'declined', at: record.declinedAt, comment: record.declinedComment ?? '', editable: true });
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
