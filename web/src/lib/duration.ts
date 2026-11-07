// A number of seconds as a person reads a duration. Presentation only: the number is the one the
// surface handed over, rounded for reading and never computed from anything else.

export function duration(seconds: number): string {
	const s = Math.max(0, Math.round(seconds));
	if (s < 60) return `${s} s`;
	const m = Math.round(s / 60);
	if (m < 60) return `${m} min`;
	const h = Math.floor(m / 60);
	const rest = m % 60;
	if (h < 48) return rest ? `${h} h ${rest} min` : `${h} h`;
	return `${Math.round(h / 24)} days`;
}

/** A number of hours the surface handed over, as hours and minutes: "3 h 20 min", or "20 min"
 * under an hour — the form the surface's own sentence uses. */
export function hoursAndMinutes(hours: number): string {
	const minutes = Math.max(0, Math.round(hours * 60));
	const h = Math.floor(minutes / 60);
	const m = minutes % 60;
	return h ? `${h} h ${m} min` : `${m} min`;
}
