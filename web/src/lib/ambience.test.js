// The ambience module is mostly Web Audio and cannot run under node, but the part that
// decides *which* bed a book gets is pure, and it is the part with a history of being
// subtly wrong: it matched substrings, so "Business/Startup Growth" hit the forest
// keyword "art" inside "st-art-up".

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { PROFILES, PROFILE_KEYS, bedForCategory } from './ambience.js';

describe('PROFILES', () => {
  it('gives every bed a name, a blurb and at least one category', () => {
    for (const key of PROFILE_KEYS) {
      const profile = PROFILES[key];
      assert.ok(profile.name, `${key} has no name`);
      assert.ok(profile.blurb, `${key} has no blurb`);
      assert.ok(profile.categories.length > 0, `${key} matches nothing`);
    }
  });

  it('keeps every modulation cycle over eight seconds', () => {
    // The design's rule: nothing unprompted may occupy the half-second-to-eight-second
    // middle, or the movement inside a bed reads as an event.
    for (const key of PROFILE_KEYS) {
      assert.ok(PROFILES[key].cycle > 8, `${key} cycles every ${PROFILES[key].cycle}s`);
    }
  });

  it('only claims a recording for beds that name a file', () => {
    for (const key of PROFILE_KEYS) {
      const { src } = PROFILES[key];
      if (src !== undefined) assert.match(src, /^\/ambience\/[a-z]+\.mp3$/, key);
    }
  });
});

describe('bedForCategory', () => {
  it('matches whole words, not substrings inside them', () => {
    // The regression that motivated the word-boundary matcher. "startup" contains
    // "art"; a startup book belongs by the river, not in the forest.
    assert.equal(bedForCategory('Business/Startup Growth'), 'river');
    // …while "art" as a word of its own still means what it says.
    assert.equal(bedForCategory('Art History'), 'forest');
    // "physics" is wind's, and must not be reached through "particle".
    assert.equal(bedForCategory('Particle Physics'), 'wind');
  });

  it('still matches multi-word keywords through the punctuation the pipeline invents', () => {
    // Every spelling below is one the LLM actually produced somewhere in books/. The
    // separator moves and the case moves; the keyword has to survive both.
    for (const category of [
      'Self-Help',
      'Self-help / Personal Development',
      'Self-help/Career Development',
      'Psychology / Self-help',
      'Psychology/ Self-Help',
      'Education & Self-Help',
      'Self-help / Personal Growth / Business & Economics',
    ]) {
      assert.equal(bedForCategory(category), 'fireplace', category);
    }
  });

  it('follows the handoff’s table for the categories it names', () => {
    const expected = {
      'Art & Photography, Cultural Studies': 'forest',
      'Computer Science': 'river',
      'Software Design': 'river',
      'Spirituality, Buddhism, Philosophy': 'lake',
      'History/Archaeology': 'lake',
      'Self-help / Personal Development': 'fireplace',
      'Science/Physics/Chemistry': 'wind',
      'Business & Marketing': 'rain',
    };
    for (const [category, bed] of Object.entries(expected)) {
      assert.equal(bedForCategory(category), bed, category);
    }
  });

  it('suggests nothing for politically charged material', () => {
    // Mood music over propaganda reads as manipulation: suggest a bed there, never
    // start one.
    for (const category of ['Political Science', 'Politics & Culture', 'Propaganda']) {
      assert.equal(bedForCategory(category), null, category);
    }
  });

  it('does not mistake an ordinary word for a political one', () => {
    // "war" is a stop word, but it must not catch "warehouse" or "software".
    assert.notEqual(bedForCategory('Warehouse Logistics'), null);
    assert.equal(bedForCategory('Software Design'), 'river');
  });

  it('falls back to the forest rather than to silence', () => {
    for (const category of ['uncategorised', '', 'Something Nobody Mapped']) {
      assert.equal(bedForCategory(category), 'forest', JSON.stringify(category));
    }
  });

  it('survives being handed nothing at all', () => {
    assert.equal(bedForCategory(), 'forest');
    assert.equal(bedForCategory(null), 'forest');
    assert.equal(bedForCategory(undefined), 'forest');
  });

  it('only ever names a bed that exists', () => {
    const samples = [
      'Business',
      'Cooking, Balinese',
      'Non-Fiction, Science, Technology and Ethics',
      'Faith and Mental Health',
      'Humor, Satire, Social Justice',
      'Studies in Jungian Psychology',
    ];
    for (const category of samples) {
      const bed = bedForCategory(category);
      if (bed !== null) assert.ok(PROFILE_KEYS.includes(bed), `${category} -> ${bed}`);
    }
  });
});
