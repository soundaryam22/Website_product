from odoo import api, fields, models, tools, _, SUPERUSER_ID


class ProductTemplate(models.Model):
    _inherit = "product.template"

    discount_percentage = fields.Integer("Discount (%)", default=0)

    # Calculate discount amount
    def get_discount_amount(self):
        disc_val = (self.discount_percentage / 100) * self.list_price
        disc_amount = self.list_price - disc_val
        return disc_amount

    # update discount value in the cart page
    def _get_additionnal_combination_info(self, product_or_template, quantity, date, website):
        pricelist = website.pricelist_id
        currency = website.currency_id

        compare_list_price = product_or_template.compare_list_price if self.env.user.has_group('website_sale.group_product_price_comparison') else None
        list_price = product_or_template._price_compute('list_price')[product_or_template.id]
        price_extra = product_or_template._get_attributes_extra_price()
        if product_or_template.currency_id != currency:
            price_extra = product_or_template.currency_id._convert(from_amount=price_extra,to_currency=currency,company=self.env.company,date=date)
            list_price = product_or_template.currency_id._convert(from_amount=list_price, to_currency=currency,company=self.env.company,date=date,)
            compare_list_price = product_or_template.currency_id._convert(from_amount=compare_list_price,to_currency=currency,company=self.env.company, date=date,round=False)

        # Pricelist price doesn't have to be converted
        pricelist_price = pricelist._get_product_price(product=product_or_template,quantity=quantity, target_currency=currency)

        if pricelist.discount_policy == 'without_discount':
            has_discounted_price = currency.compare_amounts(list_price, pricelist_price) == 1
        else:
            has_discounted_price = False

        combination_info = {
            'price_extra': price_extra,
            'price': pricelist_price,
            'list_price': list_price,
            'has_discounted_price': has_discounted_price,
            'compare_list_price': compare_list_price,
        }

        # Apply taxes
        fiscal_position = website.fiscal_position_id.sudo()

        product_taxes = product_or_template.sudo().taxes_id._filter_taxes_by_company(self.env.company)
        taxes = self.env['account.tax']
        if product_taxes:
            taxes = fiscal_position.map_tax(product_taxes)
            # We do not apply taxes on the compare_list_price value because it's meant to be
            # a strict value displayed as is.
            for price_key in ('price', 'list_price', 'price_extra'):
                combination_info[price_key] = self._apply_taxes_to_price(
                    combination_info[price_key],
                    currency,
                    product_taxes,
                    taxes,
                    product_or_template,
                )

        combination_info.update({
            'prevent_zero_price_sale': website.prevent_zero_price_sale and float_is_zero(
                combination_info['price'],
                precision_rounding=currency.rounding,
            ),

            'base_unit_name': product_or_template.base_unit_name,
            'base_unit_price': product_or_template._get_base_unit_price(combination_info['price']),

            # additional info to simplify overrides
            'currency': currency,  # displayed currency
            'date': date,
            'product_taxes': product_taxes,  # taxes before fpos mapping
            'taxes': taxes,  # taxes after fpos mapping
        })

        if pricelist.discount_policy != 'without_discount':
            # Leftover from before cleanup, different behavior between ecommerce & backend configurator
            # probably to keep product sales price hidden from customers ?
            combination_info['list_price'] = combination_info['price']

        if website.is_view_active('website_sale.product_tags') and product_or_template.is_product_variant:
            combination_info['product_tags'] = self.env['ir.ui.view']._render_template(
                'website_sale.product_tags', values={
                    'all_product_tags': product_or_template.all_product_tag_ids.filtered('visible_on_ecommerce')
                }
            )
        if self.discount_percentage > 0:
            disc_val = (self.discount_percentage / 100) * self.list_price
            disc_amount = self.list_price - disc_val
            combination_info['base_unit_price'] = disc_amount
            combination_info['price'] = disc_amount
            combination_info['list_price'] = disc_amount

        return combination_info

