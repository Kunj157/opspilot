/** Pages the static demo export pre-renders for dynamic routes (used by the layout.demo.tsx files). */
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

export const demoIncidentParams = () => [1, 2, 3, 4].map((n) => ({ incidentId: id(n) }));
export const demoServiceParams = () => [1, 2, 3, 4, 5].map((n) => ({ serviceId: id(100 + n) }));
export const demoRunbookParams = () => [0, 1, 2, 3].map((n) => ({ runbookId: id(200 + n) }));
