/**
 * Calibrate the ambience beds.
 *
 * The recordings and the synthesized beds are mastered 30-40dB apart, so each bed
 * carries a TRIM in src/lib/ambience.js that brings it to a common level. Those numbers
 * are measured with this script, not guessed — rerun it whenever a recording is
 * replaced, and paste the suggested trims back into TRIM.
 *
 *   uvicorn api.main:app --port 8000      # serving a built web/dist
 *   cd web && npm i -D playwright && node tools/measure-beds.mjs
 *
 * Set every TRIM to 1 before measuring, or you will be measuring the trims you already
 * applied. Run it twice and use the second run: the first streams the audio cold and
 * reads low while the buffer is still filling.
 */
import { chromium } from 'playwright';

// Measure each bed's level as built, so the trims can be calculated rather than guessed.
const browser = await chromium.launch({
  executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  args: ['--autoplay-policy=no-user-gesture-required'],
});
const page = await browser.newPage();
await page.goto('http://127.0.0.1:8000', { waitUntil: 'networkidle' });

const beds = ['forest', 'river', 'fireplace', 'wind', 'lake', 'rain'];
const results = {};

for (const bed of beds) {
  results[bed] = await page.evaluate(async (key) => {
    const { Ambience } = window.BookvAmbience;
    const amb = new Ambience({ level: 1 }); // master settles at MAX_GAIN = 0.5
    amb.play(key);
    const analyser = amb.ctx.createAnalyser();
    analyser.fftSize = 4096;
    amb.master.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);

    await new Promise((r) => setTimeout(r, 5200)); // past the 4s fade

    let sum = 0;
    let peak = 0;
    let frames = 0;
    for (let i = 0; i < 40; i++) {
      analyser.getFloatTimeDomainData(buf);
      for (let j = 0; j < buf.length; j++) {
        sum += buf[j] * buf[j];
        if (Math.abs(buf[j]) > peak) peak = Math.abs(buf[j]);
      }
      frames += buf.length;
      await new Promise((r) => setTimeout(r, 60));
    }
    const masterGain = amb.master.gain.value;
    amb.dispose();
    const rms = Math.sqrt(sum / frames);
    return { rms: rms / masterGain, peak: peak / masterGain }; // pre-master
  }, bed);
  const r = results[bed];
  console.log(
    `${bed.padEnd(10)} pre-master rms=${r.rms.toFixed(5)} (${(20 * Math.log10(r.rms)).toFixed(1)} dBFS)  peak=${r.peak.toFixed(4)}`,
  );
}

// A common target every bed can reach without clipping: the loudest peak decides.
const TARGET = 0.09;
console.log('\nsuggested trims for a common pre-master rms of', TARGET);
for (const bed of beds) {
  const { rms, peak } = results[bed];
  const wanted = TARGET / rms;
  const safe = 1.8 / peak; // the master caps at 0.5, so the bus clips only past 2.0
  const trim = Math.min(wanted, safe);
  console.log(
    `  ${bed.padEnd(10)} trim ${trim.toFixed(3).padStart(7)}  -> rms ${(rms * trim).toFixed(4)}  peak ${(peak * trim).toFixed(3)}${
      trim < wanted ? '   (peak-limited)' : ''
    }`,
  );
}

await browser.close();
