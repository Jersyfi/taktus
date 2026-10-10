// Where each step of a run stands on the page: a step's column is the length of the longest
// chain of steps it depends on, its row its place among the steps of that column, in the run's
// order. A layout, not a fact: it says nothing a step's dependencies do not say.

export interface Placed {
	id: string;
	column: number;
	row: number;
}

export function place(steps: { id: string; depends_on?: string[] }[]): Placed[] {
	const depth = new Map<string, number>();
	const byId = new Map(steps.map((s) => [s.id, s]));
	const visiting = new Set<string>();
	const measure = (id: string): number => {
		const known = depth.get(id);
		if (known !== undefined) return known;
		if (visiting.has(id)) return 0; // a cycle cannot be planned; drawn flat rather than lost
		visiting.add(id);
		const parents = (byId.get(id)?.depends_on ?? []).filter((p) => byId.has(p));
		const found = parents.length === 0 ? 0 : 1 + Math.max(...parents.map(measure));
		visiting.delete(id);
		depth.set(id, found);
		return found;
	};
	const rows = new Map<number, number>();
	return steps.map((s) => {
		const column = measure(s.id);
		const row = rows.get(column) ?? 0;
		rows.set(column, row + 1);
		return { id: s.id, column, row };
	});
}
