interface User {
  id: number;
  name: string;
}

function greet(user: User): string {
  return `Hello ${user.name}`;
}
