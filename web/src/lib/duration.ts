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
