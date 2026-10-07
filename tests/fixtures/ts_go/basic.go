package fixture

type User struct {
	Id   float64
	Name string
}

func Greet(user User) string {
	return "Hello " + user.Name
}
