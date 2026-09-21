import os

import matplotlib

matplotlib.use("Agg")  # headless backend: the API runs on a server without a display

import matplotlib.pyplot as plt
import seaborn as sns

# Configurations of charts
sns.set_style("whitegrid")
plt.rcParams.update({
    'font.size': 12,
    'axes.titlesize': 14,
    'axes.labelsize': 12
})


def _bar_chart(data, category, value, title, ylabel, palette, output_path, money=False):
    plt.figure(figsize=(8, 5))
    ax = sns.barplot(data=data, x=category, y=value, hue=category, palette=palette, legend=False)
    plt.title(title, fontsize=14, weight='bold')
    plt.xlabel(category)
    plt.ylabel(ylabel)

    if len(data) > 5:
        plt.xticks(rotation=45, ha='right')

    # Values above the bars
    for p in ax.patches:
        label = f'€{p.get_height():,.2f}' if money else f'{int(p.get_height())}'
        ax.annotate(label,
                    (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha='center', va='bottom', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def generate_charts(df, output_dir='assets'):
    """Save the report charts as PNGs in ``output_dir``.

    Use a separate ``output_dir`` per request when called concurrently, otherwise
    simultaneous reports overwrite each other's charts.
    """
    df = df.assign(Revenue=df['Quantity'] * df['Price'])

    os.makedirs(output_dir, exist_ok=True)

    # Total Quantity per Product
    qty_product = df.groupby('Product')['Quantity'].sum().reset_index()
    _bar_chart(qty_product, 'Product', 'Quantity', 'Total Quantity per Product',
               'Quantity', 'Blues_d', os.path.join(output_dir, 'total_quantity_per_product.png'))

    # Total Revenue per Product
    revenue_product = df.groupby('Product')['Revenue'].sum().reset_index()
    _bar_chart(revenue_product, 'Product', 'Revenue', 'Total Revenue per Product',
               'Revenue (€)', 'Purples_d', os.path.join(output_dir, 'total_revenue_per_product.png'),
               money=True)

    # Total Quantity per Seller
    qty_seller = df.groupby('Seller')['Quantity'].sum().reset_index()
    _bar_chart(qty_seller, 'Seller', 'Quantity', 'Total Quantity per Seller',
               'Quantity', 'Greens_d', os.path.join(output_dir, 'total_quantity_per_seller.png'))

    # Trend: Quantity over Time
    trend = df.groupby('Date')['Quantity'].sum().reset_index().sort_values('Date')
    plt.figure(figsize=(10, 5))
    sns.lineplot(data=trend, x='Date', y='Quantity', marker='o', color='teal', linewidth=2)
    plt.title('Quantity Trend over Time', fontsize=14, weight='bold')
    plt.xlabel('Date')
    plt.ylabel('Quantity')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'quantity_trend_over_time.png'), dpi=300)
    plt.close()
