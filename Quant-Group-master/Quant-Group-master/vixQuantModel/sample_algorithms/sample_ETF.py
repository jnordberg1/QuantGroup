'''
Sample trading algorithm for Robinhood
'''

# import pipeline methods 
from quantopian.algorithm import attach_pipeline, pipeline_output
from quantopian.pipeline import Pipeline

# import built in factors and filters
import quantopian.pipeline.factors as Factors
import quantopian.pipeline.filters as Filters

# import any datasets we need
from quantopian.pipeline.data.builtin import USEquityPricing 

# import numpy and pandas just in case
import numpy as np
import pandas as pd


# Set any algorithm 'constants' you will be using
MIN_CASH = 25.00
MIN_ADJUST_AMT = 200.00
ROBINHOOD_GOLD_BUYING_POWER = 2000.00


# Here we specify the ETFs and their associated weights
MY_ETFS = pd.DataFrame.from_items([
        (symbol('SPXL'),[ 0.50]),
        (symbol('TMF'), [0.25]),
        (symbol('EDZ'), [0.25]),
        
        ], columns = ['weight'], orient='index')


def initialize(context):
    """
    Called once at the start of the algorithm.
    """   
    
    # Create a list of daily orders (used for retrying). Initially it's empty.
    context.todays_orders = []
    
    # Set commision model for Robinhood
    set_commission(commission.PerShare(cost=0.0, min_trade_cost=0.0))

    # Ensure no short trading in Robinhood (just a precaution)
    set_long_only()
    
    # Create and attach pipeline to get data
    attach_pipeline(my_pipeline(context), name='my_pipeline')
    
    
    # Try to place orders
    schedule_function(enter_sells, date_rules.every_day(), time_rules.market_open(minutes = 10))
    schedule_function(enter_buys, date_rules.every_day(), time_rules.market_open(minutes = 30))

    # Retry any cancelled orders 3 times for 10 minutes
    schedule_function(retry_cancelled_order, date_rules.every_day(), time_rules.market_open(minutes = 35))
    schedule_function(retry_cancelled_order, date_rules.every_day(), time_rules.market_open(minutes = 45))
    schedule_function(retry_cancelled_order, date_rules.every_day(), time_rules.market_open(minutes = 55))
    
    # Record tracking variables at the end of each day.
    schedule_function(my_record_vars, date_rules.every_day(), time_rules.market_close())

    
def my_pipeline(context):
    '''
    Define the pipline data columns
    '''
    
    # Create filter for just the ETFs we want to trade
    universe = Filters.StaticAssets(MY_ETFS.index)
           
    # Create any factors we need
    # latest_price is just used in case we don't have current price for an asset
    latest_price = Factors.Latest(inputs =[USEquityPricing.close], mask=universe)
       
    return Pipeline(
            columns = {
            'latest_price' : latest_price,
            },
            screen = universe,
            )


def before_trading_start(context, data):
    
    # Clear the list of todays orders and start fresh
    # Would like to do this 'context.today_orders.clear()' but not supported
    del context.todays_orders[:]
    
    # Get the data
    context.output = pipeline_output('my_pipeline')
    
    # Add other columns to the dataframe for storing qty of shares held, etc
    context.output = context.output.assign(
        held_shares = 0,
        target_shares = 0,
        order_shares = 0,
        target_value = 0.0,
        order_value = 0.0,
        weight = MY_ETFS.weight,
    )
    
    update_stock_data(context, context.output, data)

                 
def enter_sells(context, data):
    
    update_stock_data(context, context.output, data)
    
    # We want to sell anything less than our min number of shares
    rules = 'order_value < -@MIN_ADJUST_AMT'
    sells = context.output.query(rules).index.tolist()
    
    for stock in sells:
        order_id = order(stock, 
              context.output.get_value(stock, 'order_shares'),
              style=LimitOrder(context.output.get_value(stock, 'latest_price'))
              )
        context.todays_orders.append(order_id)


def enter_buys(context, data):
    
    update_stock_data(context, context.output, data)
    adjust_buy_orders_per_available_cash(context, data)
    
    # We want to buy anything greater than our min number of shares
    rules = 'order_value > @MIN_ADJUST_AMT'
    buys = context.output.query(rules).index.tolist()
    
    for stock in buys:
        order_id = order(stock, 
              context.output.get_value(stock, 'order_shares'),
              style=LimitOrder(context.output.get_value(stock, 'latest_price'))
              )
        context.todays_orders.append(order_id)


def update_stock_data(context, output_df, data):
    # Determine portfolio value we want to call '100%'
    target_portfolio_value = context.portfolio.portfolio_value + ROBINHOOD_GOLD_BUYING_POWER - MIN_CASH
    context.target_portfolio_value = target_portfolio_value
    
    # Update the shares held for any security we hold
    # If we don't hold a security held_shares keeps the default value of 0
    for security, position in context.portfolio.positions.items(): 
        output_df.set_value(security, 'held_shares', position.amount)
        
    # Get the latest prices for all our securities
    # May want to account for possibility of price being NaN or 0?
    output_df.latest_price = data.current(output_df.index, 'price')
                     
    # Calculate amounts (note the // operator is the python floor function)
    output_df.target_value = output_df.weight * target_portfolio_value
    output_df.target_shares = output_df.target_value // output_df.latest_price

    output_df.order_shares = output_df.target_shares - output_df.held_shares
    output_df.order_value = output_df.order_shares * output_df.latest_price


def adjust_buy_orders_per_available_cash(context, data):
    # If order_shares is positive then we want to buy more
    required_cash = (context.output
                     .query('order_shares > 0')
                     .order_value.sum(axis=0)
                     )
    net_cash = context.portfolio.cash + ROBINHOOD_GOLD_BUYING_POWER - MIN_CASH
    
    if required_cash < net_cash and net_cash > 0.0:
        # We're good to go
        pass
    
    elif required_cash > 0.0 and net_cash > 0.0:
        # required_cash should always be > 0 but checking anyway
        reduce_by_ratio = required_cash / net_cash 
        context.output.order_shares = (context.output.query('order_shares > 0')
                                       .order_shares // reduce_by_ratio
                                       )
    else:
        # net cash is negative so don't buy anything
        context.output.order_shares = (context.output.query('order_shares > 0')
                                       .order_shares * 0.0
                                       )    
    
    # Calculate the new order_value since we changed the order shares
    # Do the calc for the whole dataframe but really just need to do the 'order_shares > 0'
    context.output.order_value = context.output.order_shares * context.output.latest_price

    adjusted_cash = (context.output
                     .query('order_shares >= 0')
                     .order_value.sum(axis=0)
                     )
    if adjusted_cash >= net_cash:
        # Just checking to make sure
        log.info('got a problem %f  %f' % (adjusted_cash, net_cash))
        
        
def retry_cancelled_order(context, data):
    for order_id in context.todays_orders[:]:
        my_order = get_order(order_id)
        if my_order and my_order.status == 2 :
            # The order was somehow cancelled so retry
            order_id = order(
                my_order.sid, 
                my_order.amount,
                style=LimitOrder(my_order.limit)
                )
            context.todays_orders.append(order_id)
            log.info('order for %i shares of %s cancelled - retrying' % (my_order.amount, my_order.sid))
            # Remove the original order (typically can't do but note the [:]
            context.todays_orders.remove(order_id)


def my_record_vars(context, data):
    """
    Plot variables at the end of each day.
    """
            
    record(cash=context.portfolio.cash)

