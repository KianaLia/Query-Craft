from django.core.management.base import BaseCommand
from faker import Faker
import random
from django.utils import timezone
from nl2sql_app.models import Customer, Product, Order
from django.db import transaction

class Command(BaseCommand):
    help = 'Seed DB with fake customers, products, and orders'

    def add_arguments(self, parser):
        parser.add_argument('--customers', type=int, default=300)
        parser.add_argument('--products', type=int, default=100)
        parser.add_argument('--orders', type=int, default=1000)

    def handle(self, *args, **options):
        fake = Faker()
        customers_count = options['customers']
        products_count = options['products']
        orders_count = options['orders']

        self.stdout.write('Seeding database...')
        with transaction.atomic():
           
            Order.objects.all().delete()
            Customer.objects.all().delete()
            Product.objects.all().delete()

            customers = []
            for _ in range(customers_count):
                customers.append(Customer(
                    name=fake.name(),
                    email=fake.unique.email(),
                    registration_date=fake.date_time_between(start_date='-2y', end_date='now', tzinfo=timezone.get_current_timezone())
                ))
            Customer.objects.bulk_create(customers)
            customers = list(Customer.objects.all())


            categories = ['electronics','books','clothing','home','sports','beauty']
            products = []
            for _ in range(products_count):
                products.append(Product(
                    name=(fake.word().title() + ' ' + fake.word().title()),
                    category=random.choice(categories),
                    price=round(random.uniform(5, 500), 2)
                ))
            Product.objects.bulk_create(products)
            products = list(Product.objects.all())

            statuses = ['pending','shipped','delivered','cancelled','returned']
            orders = []
            for _ in range(orders_count):
                orders.append(Order(
                    customer=random.choice(customers),
                    product=random.choice(products),
                    order_date=fake.date_time_between(start_date='-1y', end_date='now', tzinfo=timezone.get_current_timezone()),
                    quantity=random.randint(1,5),
                    status=random.choice(statuses)
                ))
            Order.objects.bulk_create(orders, batch_size=1000)

        self.stdout.write(self.style.SUCCESS('Seeding done.'))
