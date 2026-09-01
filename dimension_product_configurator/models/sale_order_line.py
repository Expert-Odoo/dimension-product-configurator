# Dimension Product Configurator - sale.order.line integration
from odoo import models, fields, api
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dim_product_id = fields.Many2one(
        'dimension_config.product', string='Configurable Product',
        compute='_compute_dim_product_id', store=True,
    )
    dim_configuration_id = fields.Many2one(
        'dimension_config.configuration', string='Configuration',
        ondelete='set null', copy=False,
    )
    dim_summary = fields.Text(
        'Configuration Summary', related='dim_configuration_id.summary',
        store=True,
    )
    is_dim_config = fields.Boolean(
        compute='_compute_dim_product_id', store=True,
    )

    @api.depends('product_id')
    def _compute_dim_product_id(self):
        for line in self:
            if line.product_id:
                cpq = self.env['dimension_config.product'].search([
                    ('product_tmpl_id', '=', line.product_id.product_tmpl_id.id)
                ], limit=1)
                line.dim_product_id = cpq
                line.is_dim_config = bool(cpq)
            else:
                line.dim_product_id = False
                line.is_dim_config = False

    def _compute_display_name(self):
        """Affiche 'Produit [× qté] [✓]' dans le sélecteur CPQ, comportement standard ailleurs."""
        if self.env.context.get('cpq_selector'):
            for line in self:
                qty = f"{line.product_uom_qty:.0f} × " if line.product_uom_qty != 1 else ""
                status = " ✓" if line.dim_configuration_id else " ○"
                line.display_name = f"{qty}{line.product_id.name}{status}"
        else:
            super()._compute_display_name()

    def action_configure_dim(self):
        self.ensure_one()
        if not self.dim_product_id:
            return
        if not self.id:
            raise UserError(
                "Please save the quotation before configuring the product."
            )
        wizard_vals = {
            'sale_line_id': self.id,
            'dim_product_id': self.dim_product_id.id,
        }
        wizard = self.env['dimension_config.configurator.wizard'].create(wizard_vals)
        wizard._init_lines()  # appelé explicitement après create()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Configure Product',
            'res_model': 'dimension_config.configurator.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'dialog_size': 'medium'},
        }


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dim_line_count = fields.Integer(
        'Configurable Lines',
        compute='_compute_dim_line_count',
    )
    dim_unconfigured_count = fields.Integer(
        'Unconfigured Lines',
        compute='_compute_dim_line_count',
    )

    @api.depends('order_line.is_dim_config', 'order_line.dim_configuration_id')
    def _compute_dim_line_count(self):
        for order in self:
            cpq_lines = order.order_line.filtered('is_dim_config')
            order.dim_line_count = len(cpq_lines)
            order.dim_unconfigured_count = len(
                cpq_lines.filtered(lambda l: not l.dim_configuration_id)
            )

    def action_configure_dim_lines(self):
        """Ouvre le configurateur CPQ.

        - 1 ligne CPQ → ouvre directement le wizard
        - Plusieurs lignes → affiche une liste de sélection
        """
        self.ensure_one()
        cpq_lines = self.order_line.filtered('is_dim_config')
        if not cpq_lines:
            return

        if len(cpq_lines) == 1:
            return cpq_lines[0].action_configure_dim()

        # Plusieurs lignes → wizard de sélection
        selector = self.env['dimension_config.line.selector'].create({
            'order_id': self.id,
            'line_id': cpq_lines.filtered(lambda l: not l.dim_configuration_id)[:1].id
                       or cpq_lines[0].id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Choose a product to configure',
            'res_model': 'dimension_config.line.selector',
            'res_id': selector.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'cpq_selector': True},
        }


class CpqLineSelector(models.TransientModel):
    """Wizard de sélection de la ligne CPQ à configurer (cas multi-lignes)."""
    _name = 'dimension_config.line.selector'
    _description = 'Configurable Line Selection'

    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade')
    line_id = fields.Many2one(
        'sale.order.line',
        string='Product to configure',
        domain="[('order_id', '=', order_id), ('is_dim_config', '=', True)]",
        required=True,
    )
    line_summary = fields.Text(
        related='line_id.dim_summary', string='Current configuration', readonly=True,
    )

    def action_open_configurator(self):
        self.ensure_one()
        return self.line_id.action_configure_dim()
