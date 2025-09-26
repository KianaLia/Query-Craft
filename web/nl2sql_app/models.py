from django.db import models

class Customer(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    registration_date = models.DateTimeField()

    def __str__(self):
        return f"{self.name} <{self.email}>"

class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.name

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending','pending'),
        ('shipped','shipped'),
        ('delivered','delivered'),
        ('cancelled','cancelled'),
        ('returned','returned'),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    order_date = models.DateTimeField()
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    def __str__(self):
        return f"Order {self.id} - {self.customer_id} - {self.product_id}"
