import { api } from "../api/client";

/** Class codes use the same 30-character alphabet as the server (no 0/1/I/L/O). */
export const CODE_ALPHABET = /^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$/;

/**
 * Parse a student ID as a student might type it: `CE4R-12`, `ce4r 12`, `CE4R–12` (en dash).
 * Returns the upper-cased code and the register number, or null when it is not an ID.
 */
export function parseStudentId(text: string): { code: string; reg_no: number } | null {
  const m = text.trim().match(/^([A-Za-z0-9]{4})\s*[-–—_/:.]?\s*(\d{1,3})$/);
  if (!m) return null;
  const code = m[1].toUpperCase();
  if (!CODE_ALPHABET.test(code)) return null;
  const reg_no = Number(m[2]);
  if (!Number.isInteger(reg_no) || reg_no < 1) return null;
  return { code, reg_no };
}

/** Student routes use the same client — the `sms_student` cookie is same-origin. */
export const studentApi = api;
